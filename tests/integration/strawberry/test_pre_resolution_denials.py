"""Pre-resolution denials: FORBIDDEN / NULL / NOT_FOUND."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
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


def _engine_with_surface(
    surface: DenialSurface,
) -> PolicyEngine[Principal[Actor, str], Action, Article]:
    engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

    @engine.policy(
        action=Action.READ,
        subject_type=Article,
        denial_surface=surface,
    )
    def _pol(p: Principal[Actor, str], s: Article) -> Decision:
        if s.is_published or p.actor.is_admin or p.actor.user_id == s.owner_id:
            return ALLOW
        return deny("article_unpublished")

    return engine


def _schema_with_resolver_spy(
    engine: PolicyEngine[Principal[Actor, str], Action, Article],
    *,
    optional: bool = False,
) -> tuple[strawberry.Schema, AsyncMock]:
    resolver_spy = AsyncMock(return_value="resolved-value")

    @strawberry.type
    class Query:
        @strawberry.field(
            extensions=[
                policy_guard(
                    engine=engine,
                    principal_loader=principal_from_ctx,
                    action=Action.READ,
                    subject_type=Article,
                    load_subject=load_article,
                )
            ],
        )
        async def article(
            self,
            article_id: strawberry.ID,
        ) -> str | None:
            del article_id
            value: str = await resolver_spy()
            return value

    return strawberry.Schema(query=Query), resolver_spy


class TestForbiddenDenial:
    def test_denied_caller_gets_graphql_error_no_resolver_invocation(
        self,
    ) -> None:
        engine = _engine_with_surface(DenialSurface.FORBIDDEN)
        schema, resolver_spy = _schema_with_resolver_spy(engine)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        ctx = make_ctx(stranger)

        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{UNPUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )

        assert_that(result.errors).is_not_none()
        assert_that(len(result.errors or [])).is_greater_than_or_equal_to(1)
        assert_that(result.data).is_not_none()
        # Resolver MUST NOT have executed.
        assert_that(resolver_spy.await_count).is_equal_to(0)


class TestNullDenial:
    def test_null_returns_null_skipping_resolver(self) -> None:
        engine = _engine_with_surface(DenialSurface.NULL)
        schema, resolver_spy = _schema_with_resolver_spy(engine)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        ctx = make_ctx(stranger)

        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{UNPUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )

        # No top-level error -- field masked to null.
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": None})
        # Resolver MUST NOT have executed.
        assert_that(resolver_spy.await_count).is_equal_to(0)

    def test_null_allowed_caller_runs_resolver(self) -> None:
        engine = _engine_with_surface(DenialSurface.NULL)
        schema, resolver_spy = _schema_with_resolver_spy(engine)
        admin = Actor(user_id=uuid4(), is_admin=True)
        ctx = make_ctx(admin)

        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{UNPUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )

        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "resolved-value"})
        assert_that(resolver_spy.await_count).is_equal_to(1)


class TestNotFoundDenial:
    def test_unknown_subject_returns_not_found(self) -> None:
        engine = _engine_with_surface(DenialSurface.FORBIDDEN)
        schema, resolver_spy = _schema_with_resolver_spy(engine)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        ctx = make_ctx(stranger)
        bogus_id = uuid4()
        # Make sure the id is truly unknown.
        assert bogus_id not in ARTICLES  # narrow: precondition

        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{bogus_id}") }}',
                context_value=ctx,
            )
        )

        # The adapter raises ResourceNotFound; Strawberry surfaces this
        # as a field-level error.
        assert_that(result.errors).is_not_none()
        assert_that(resolver_spy.await_count).is_equal_to(0)

    def test_published_article_visible_to_stranger(self) -> None:
        engine = _engine_with_surface(DenialSurface.FORBIDDEN)
        schema, resolver_spy = _schema_with_resolver_spy(engine)
        stranger = Actor(user_id=uuid4(), is_admin=False)
        ctx = make_ctx(stranger)

        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )

        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"article": "resolved-value"})
        assert_that(resolver_spy.await_count).is_equal_to(1)
