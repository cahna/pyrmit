"""Per-request principal caching: principal loader called once."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import strawberry
from assertpy import assert_that
from strawberry.types import Info

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    PUBLISHED_ID,
    Action,
    Actor,
    Article,
    load_article,
    make_ctx,
    principal_from_ctx,
)


class TestPrincipalCachedOncePerRequest:
    def test_one_loader_call_per_request_across_two_fields(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Article)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

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
            async def article_a(self, article_id: strawberry.ID) -> str:
                del article_id
                return "a"

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
            async def article_b(self, article_id: strawberry.ID) -> str:
                del article_id
                return "b"

        schema = strawberry.Schema(query=Query)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ articleA(articleId: "{PUBLISHED_ID}") articleB(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"articleA": "a", "articleB": "b"})
        # Exactly one principal_loader invocation despite two guarded fields.
        assert_that(ctx.principal_loader_calls).is_equal_to(1)

    def test_distinct_context_objects_get_distinct_principals(self) -> None:
        """Regression: principal must NEVER leak across requests.

        The cache is keyed by ``info.context`` identity in a
        ``WeakKeyDictionary``; two requests with two different context
        objects must each see their own loader invocation and must
        not observe a stale principal from a prior request.
        """
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Article)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

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
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        actor_a = Actor(user_id=uuid4(), is_admin=True)
        actor_b = Actor(user_id=uuid4(), is_admin=True)
        ctx_a = make_ctx(actor_a)
        ctx_b = make_ctx(actor_b)

        query_str = f'{{ article(articleId: "{PUBLISHED_ID}") }}'
        result_a = asyncio.run(schema.execute(query_str, context_value=ctx_a))
        result_b = asyncio.run(schema.execute(query_str, context_value=ctx_b))

        assert_that(result_a.errors).is_none()
        assert_that(result_b.errors).is_none()
        # Each context's loader fired exactly once -- no cross-request leak.
        assert_that(ctx_a.principal_loader_calls).is_equal_to(1)
        assert_that(ctx_b.principal_loader_calls).is_equal_to(1)

    def test_distinct_loaders_do_not_share_cache(self) -> None:
        """Two factories with different principal loaders on the SAME context must not cross-pollinate.

        Regression for a bug where the principal cache was keyed only by
        ``info.context`` identity: a second guard built with a *different*
        ``principal_loader`` on the same request would silently reuse the
        first guard's cached principal instead of running its own loader.
        """
        calls: list[str] = []
        seen_actors: list[str] = []

        def loader_a(info: Info[Any, Any]) -> Principal[str, str]:
            del info
            calls.append("a")
            return Principal(actor="actor-a", entitlements=Entitlements.empty())

        def loader_b(info: Info[Any, Any]) -> Principal[str, str]:
            del info
            calls.append("b")
            return Principal(actor="actor-b", entitlements=Entitlements.empty())

        engine: PolicyEngine[Principal[str, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Article)
        def _pol(p: Principal[str, str], _s: Article) -> Decision:
            seen_actors.append(p.actor)
            return ALLOW

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=engine,
                        principal_loader=loader_a,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article_a(self, article_id: strawberry.ID) -> str:
                del article_id
                return "a"

            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=engine,
                        principal_loader=loader_b,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article_b(self, article_id: strawberry.ID) -> str:
                del article_id
                return "b"

        schema = strawberry.Schema(query=Query)
        # A single context shared by both fields on a single request --
        # this is the scenario the module-level, context-only cache key
        # got wrong.
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ articleA(articleId: "{PUBLISHED_ID}") articleB(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"articleA": "a", "articleB": "b"})
        # Field B's policy must see loader B's principal, not loader A's.
        assert_that(seen_actors).is_equal_to(["actor-a", "actor-b"])
        # Each loader ran exactly once despite sharing a request context.
        assert_that(calls.count("a")).is_equal_to(1)
        assert_that(calls.count("b")).is_equal_to(1)
