"""``post_resolution_policy_guard`` -- post-resolution redaction factory.

The factory is the explicit, safer counterpart to
``policy_guard(load_subject_after=...)``: it carries a ``read_only=True``
default that refuses to run inside a mutation operation (because the
resolver runs BEFORE the authorization check, mutations would let side
effects fire before the policy decides). This file verifies behavioral
equivalence on a query (denial replaces the resolver's value, allow
passes it through) AND the mutation refusal.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard, post_resolution_policy_guard
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    ARTICLES,
    UNPUBLISHED_ID,
    Action,
    Actor,
    Article,
    make_ctx,
    principal_from_ctx,
)


class TestPostResolutionPolicyGuard:
    def test_factory_returns_a_field_extension(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ_FIELD, subject_type=Article, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        guard = post_resolution_policy_guard(
            engine=engine,
            principal_loader=principal_from_ctx,
            action=Action.READ_FIELD,
            subject_type=Article,
            load_subject_after=load_after,
        )
        assert_that(hasattr(guard, "resolve_async")).is_true()

    def test_factory_denial_replaces_resolved_value_with_null(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ_FIELD, subject_type=Article, denial_surface=DenialSurface.NULL)
        def _pol(p: Principal[Actor, str], s: Article) -> Decision:
            if s.is_published or p.actor.is_admin:
                return ALLOW
            return deny("unpublished_field")

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    post_resolution_policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ_FIELD,
                        subject_type=Article,
                        load_subject_after=load_after,
                    )
                ],
            )
            async def title(self) -> str | None:
                return "secret"

        schema = strawberry.Schema(query=Query)

        stranger = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        denied = asyncio.run(schema.execute("{ title }", context_value=stranger))
        assert_that(denied.data).is_equal_to({"title": None})

        admin = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        allowed = asyncio.run(schema.execute("{ title }", context_value=admin))
        assert_that(allowed.errors).is_none()
        assert_that(allowed.data).is_equal_to({"title": "secret"})

    def test_default_read_only_blocks_mutation_before_resolver_runs(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ_FIELD, subject_type=Article, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        side_effects: list[str] = []

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        @strawberry.type
        class Query:
            @strawberry.field
            def noop(self) -> str:
                return "ok"

        @strawberry.type
        class Mutation:
            @strawberry.field(
                extensions=[
                    post_resolution_policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ_FIELD,
                        subject_type=Article,
                        load_subject_after=load_after,
                    )
                ],
            )
            async def do_thing(self) -> str:
                side_effects.append("resolver_ran")
                return "done"

        schema = strawberry.Schema(query=Query, mutation=Mutation)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(schema.execute("mutation { doThing }", context_value=ctx))

        assert_that(side_effects).is_empty()
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        assert_that(str(result.errors[0])).contains("post_resolution_guard_on_mutation_blocked")

    def test_policy_guard_load_subject_after_blocks_mutation_before_resolver_runs(self) -> None:
        """Regression: the legacy post-resolution path must share the same
        mutation safety default as ``post_resolution_policy_guard``.

        ``policy_guard(load_subject_after=...)`` creates the same
        post-resolution execution order: resolver first, policy second.
        On mutations that order can fire a side effect before auth, so
        it must block by default too.
        """
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ_FIELD, subject_type=Article, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        side_effects: list[str] = []

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        @strawberry.type
        class Query:
            @strawberry.field
            def noop(self) -> str:
                return "ok"

        @strawberry.type
        class Mutation:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ_FIELD,
                        subject_type=Article,
                        load_subject_after=load_after,
                    )
                ],
            )
            async def do_thing(self) -> str:
                side_effects.append("resolver_ran")
                return "done"

        schema = strawberry.Schema(query=Query, mutation=Mutation)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(schema.execute("mutation { doThing }", context_value=ctx))

        assert_that(side_effects).is_empty()
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        assert_that(str(result.errors[0])).contains("post_resolution_guard_on_mutation_blocked")

    def test_read_only_false_opts_in_to_mutation_use(self) -> None:
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

        @engine.policy(action=Action.READ_FIELD, subject_type=Article, denial_surface=DenialSurface.NULL)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        side_effects: list[str] = []

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        @strawberry.type
        class Query:
            @strawberry.field
            def noop(self) -> str:
                return "ok"

        @strawberry.type
        class Mutation:
            @strawberry.field(
                extensions=[
                    post_resolution_policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ_FIELD,
                        subject_type=Article,
                        load_subject_after=load_after,
                        read_only=False,
                    )
                ],
            )
            async def do_thing(self) -> str:
                side_effects.append("resolver_ran")
                return "done"

        schema = strawberry.Schema(query=Query, mutation=Mutation)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(schema.execute("mutation { doThing }", context_value=ctx))

        assert_that(side_effects).is_equal_to(["resolver_ran"])
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"doThing": "done"})
