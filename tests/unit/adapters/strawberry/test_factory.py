"""``PolicyGuardFactory`` -- partial application of engine + principal loader.

The factory exists so consumers don't restate ``engine=...`` and
``principal_loader=...`` on every field. Behaviorally it MUST be
equivalent to calling :func:`policy_guard` /
:func:`post_resolution_policy_guard` with the captured deps; these
tests verify that.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import (
    PolicyGuardFactory,
    policy_guard,
    post_resolution_policy_guard,
)
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.lazy import Lazy
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    ARTICLES,
    PUBLISHED_ID,
    UNPUBLISHED_ID,
    Action,
    Actor,
    Article,
    load_article,
    make_ctx,
    principal_from_ctx,
)


def _engine_with_owner_rule() -> PolicyEngine[Principal[Actor, str], Action, Article]:
    engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

    @engine.policy(
        action=Action.READ,
        subject_type=Article,
        denial_surface=DenialSurface.FORBIDDEN,
    )
    def _pol(p: Principal[Actor, str], s: Article) -> Decision:
        if s.is_published or p.actor.is_admin:
            return ALLOW
        return deny("unpublished")

    return engine


class TestPolicyGuardFactory:
    def test_factory_is_frozen_dataclass(self) -> None:
        """``PolicyGuardFactory`` is immutable so it can be safely captured
        at module scope and shared across schema construction."""
        engine = _engine_with_owner_rule()
        factory = PolicyGuardFactory(engine=engine, principal_loader=principal_from_ctx)
        # setattr avoids the static "cannot assign to frozen field" check;
        # the runtime FrozenInstanceError (subclass of AttributeError) is
        # what we actually want to assert here.
        try:
            setattr(factory, "engine", engine)  # noqa: B010
        except AttributeError:
            return
        assert_that(False).described_as("expected frozen instance").is_true()

    def test_explicitly_parameterized_factory_builds_working_guard(self) -> None:
        """A factory spelled with explicit type parameters composes at
        runtime (frozen dataclass + PEP 695 generics) and produces a guard
        behaviorally identical to the inferred form."""
        engine = _engine_with_owner_rule()
        factory: PolicyGuardFactory[Principal[Actor, str], Action, Article] = PolicyGuardFactory(
            engine=engine,
            principal_loader=principal_from_ctx,
        )

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
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
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "ok"})

    def test_guard_delegates_to_policy_guard_for_pre_resolution_allow(self) -> None:
        engine = _engine_with_owner_rule()
        factory = PolicyGuardFactory(engine=engine, principal_loader=principal_from_ctx)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
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
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "ok"})

    def test_guard_delegates_to_policy_guard_for_pre_resolution_deny(self) -> None:
        engine = _engine_with_owner_rule()
        factory = PolicyGuardFactory(engine=engine, principal_loader=principal_from_ctx)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
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
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{UNPUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        # FORBIDDEN surface -> GraphQL error.
        assert_that(result.errors).is_not_none()

    def test_factory_accepts_lazy_engine(self) -> None:
        """``engine`` accepts a ``Lazy`` resolver too, mirroring the bare
        :func:`policy_guard` parameter."""
        engine = _engine_with_owner_rule()
        observed: list[object] = []

        def from_ctx(info: Any) -> PolicyEngine[Principal[Actor, str], Action, Article]:
            observed.append(info)
            return engine

        factory = PolicyGuardFactory(
            engine=Lazy(from_ctx),
            principal_loader=principal_from_ctx,
        )

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
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
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        # The Lazy resolver was invoked with Strawberry Info.
        assert_that(observed).is_length(1)
        assert_that(hasattr(observed[0], "context")).is_true()

    def test_post_resolution_guard_delegates(self) -> None:
        """``factory.post_resolution_guard(...)`` behaves like the bare
        :func:`post_resolution_policy_guard` it forwards to."""
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(
            action=Action.READ_FIELD,
            subject_type=Article,
            denial_surface=DenialSurface.NULL,
        )
        def _pol(p: Principal[Actor, str], s: Article) -> Decision:
            if s.is_published or p.actor.is_admin:
                return ALLOW
            return deny("unpublished_field")

        async def load_after(_result: object, _info: Any) -> Article | None:
            return ARTICLES[UNPUBLISHED_ID]

        factory = PolicyGuardFactory(engine=engine, principal_loader=principal_from_ctx)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.post_resolution_guard(
                        action=Action.READ_FIELD,
                        subject_type=Article,
                        load_subject_after=load_after,
                    )
                ],
            )
            async def title(self) -> str | None:
                return "secret-title"

        schema = strawberry.Schema(query=Query)

        stranger = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        denied = asyncio.run(schema.execute("{ title }", context_value=stranger))
        # NULL denial surface -> field redacted to null.
        assert_that(denied.data).is_equal_to({"title": None})

        admin = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        allowed = asyncio.run(schema.execute("{ title }", context_value=admin))
        assert_that(allowed.data).is_equal_to({"title": "secret-title"})

    def test_bare_and_factory_extensions_are_equivalently_typed(self) -> None:
        """A guard built via the factory and one built via the bare
        function are both ``FieldExtension`` instances; the factory adds
        no runtime wrapping that would break Strawberry's extension
        machinery.
        """
        engine = _engine_with_owner_rule()
        factory = PolicyGuardFactory(engine=engine, principal_loader=principal_from_ctx)

        bare = policy_guard(
            engine=engine,
            principal_loader=principal_from_ctx,
            action=Action.READ,
            subject_type=Article,
            load_subject=load_article,
        )
        via_factory = factory.guard(
            action=Action.READ,
            subject_type=Article,
            load_subject=load_article,
        )
        assert_that(type(bare)).is_equal_to(type(via_factory))

        async def load_after(_r: object, _i: Any) -> Article | None:
            return ARTICLES[UNPUBLISHED_ID]

        bare_post = post_resolution_policy_guard(
            engine=engine,
            principal_loader=principal_from_ctx,
            action=Action.READ,
            subject_type=Article,
            load_subject_after=load_after,
        )
        via_factory_post = factory.post_resolution_guard(
            action=Action.READ,
            subject_type=Article,
            load_subject_after=load_after,
        )
        assert_that(type(bare_post)).is_equal_to(type(via_factory_post))
