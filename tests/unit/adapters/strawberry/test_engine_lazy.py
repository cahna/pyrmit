"""``policy_guard`` accepts ``Lazy[PolicyEngine]`` for DI use cases.

Adapters integrated into FastAPI / Starlette typically wire their
dependencies via the per-request context rather than module-level
globals. ``policy_guard(engine=Lazy(...))`` lets the call site defer
engine resolution until the field is actually executed, so the engine
(or a request-scoped collaborator graph behind it) can come from
``info.context``.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.adapters.strawberry.exceptions import PermissionDenied
from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.lazy import Lazy
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    PUBLISHED_ID,
    UNPUBLISHED_ID,
    Action,
    Actor,
    Article,
    load_article,
)


def _make_engine() -> PolicyEngine[Principal[Actor, str], Action, Article]:
    engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Article)
    def _read(principal: Principal[Actor, str], article: Article) -> Decision:
        if principal.actor.is_admin:
            return ALLOW
        if article.is_published:
            return ALLOW
        return deny("unpublished")

    return engine


class _EngineCarryingContext:
    """Context whose ``authz_engine`` attribute carries the engine.

    Mirrors how a real Strawberry context (built per-request from
    FastAPI DI) would expose an app-scoped engine.
    """

    def __init__(
        self,
        *,
        engine: PolicyEngine[Principal[Actor, str], Action, Article],
        actor: Actor,
    ) -> None:
        from pyrmit.core.entitlements import Entitlements

        self.authz_engine = engine
        self.principal = Principal[Actor, str](actor=actor, entitlements=Entitlements[str].empty())
        self.engine_resolves = 0


def _principal_from_ctx(info: Any) -> Principal[Actor, str]:
    return info.context.principal  # type: ignore[no-any-return]


def _make_engine_ctx(
    *,
    engine: PolicyEngine[Principal[Actor, str], Action, Article],
    actor: Actor,
) -> _EngineCarryingContext:
    return _EngineCarryingContext(engine=engine, actor=actor)


class TestLazyEngineResolution:
    def test_lazy_engine_is_resolved_from_context_and_allow_passes(self) -> None:
        engine = _make_engine()

        def from_ctx(info: Any) -> PolicyEngine[Principal[Actor, str], Action, Article]:
            return info.context.authz_engine  # type: ignore[no-any-return]

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=Lazy(from_ctx),
                        principal_loader=_principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        ctx = _make_engine_ctx(engine=engine, actor=Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "ok"})

    def test_lazy_engine_deny_path_uses_resolved_engine_binding(self) -> None:
        engine = _make_engine()

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=Lazy(lambda info: info.context.authz_engine),
                        principal_loader=_principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        ctx = _make_engine_ctx(engine=engine, actor=Actor(user_id=uuid4(), is_admin=False))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{UNPUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        # Default binding surface is FORBIDDEN -> PermissionDenied raised.
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        assert_that(result.errors).is_length(1)
        assert_that(result.errors[0].original_error).is_instance_of(PermissionDenied)

    def test_lazy_engine_supports_async_resolver(self) -> None:
        engine = _make_engine()

        async def aresolve(info: Any) -> PolicyEngine[Principal[Actor, str], Action, Article]:
            return info.context.authz_engine  # type: ignore[no-any-return]

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=Lazy(aresolve),
                        principal_loader=_principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "async-ok"

        schema = strawberry.Schema(query=Query)
        ctx = _make_engine_ctx(engine=engine, actor=Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "async-ok"})

    def test_lazy_engine_resolver_is_called_with_strawberry_info(self) -> None:
        engine = _make_engine()
        observed: list[object] = []

        def from_ctx(info: Any) -> PolicyEngine[Principal[Actor, str], Action, Article]:
            observed.append(info)
            return info.context.authz_engine  # type: ignore[no-any-return]

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=Lazy(from_ctx),
                        principal_loader=_principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        ctx = _make_engine_ctx(engine=engine, actor=Actor(user_id=uuid4(), is_admin=True))
        asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(observed).is_length(1)
        # The argument passed must expose .context (i.e., Strawberry Info).
        assert_that(hasattr(observed[0], "context")).is_true()
