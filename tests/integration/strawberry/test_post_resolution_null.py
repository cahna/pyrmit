"""Post-resolution NULL: resolver runs, value replaced with null."""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard
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


class TestPostResolutionNull:
    def test_post_resolution_null_drops_value_before_serialization(self) -> None:
        """The resolver runs, the article is loaded after, and a denied
        decision replaces the resolved value with None.

        Setup: the field resolver returns the article's title. The
        loader inspects the *resolved* article and decides. For
        unpublished articles + non-admin actors, the resolver's
        returned title MUST NOT cross the wire.
        """
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

        secret_title = "TOP-SECRET-ARTICLE-TITLE"

        async def load_after(result: object, info: Any) -> Article | None:
            del info, result
            return ARTICLES[UNPUBLISHED_ID]

        @strawberry.type
        class Query:
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
            async def title(self) -> str | None:
                return secret_title

        schema = strawberry.Schema(query=Query)

        # Stranger: denied -> value replaced with null
        stranger = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        result = asyncio.run(schema.execute("{ title }", context_value=stranger))
        # The resolver's value MUST NOT appear in the serialized output.
        rendered = json.dumps({
            "data": result.data,
            "errors": [str(e) for e in (result.errors or [])],
        })
        assert_that(secret_title in rendered).described_as("secret title leaked into response").is_false()
        assert_that(result.data).is_equal_to({"title": None})

        # Admin: allowed -> resolver value preserved
        admin = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(schema.execute("{ title }", context_value=admin))
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"title": secret_title})
