"""Strawberry adapter: pre-resolution loader from parent source value.

Closes an integration-test gap: ``policy_guard``'s
``load_subject_from_source`` phase had unit coverage for arity validation
only -- the runtime path was exercised only via coverage. This test
builds a real Strawberry schema where a field guard reads the subject
from the parent type's source value.
"""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID, uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    Action,
    Actor,
    Article,
    make_ctx,
    principal_from_ctx,
)

# Module-level engine + bindings reused across the from-source tests.
# Strawberry requires types referenced in schemas to be resolvable from
# global module scope, so the schema types live here too.
_ENGINE_OWNER_GATE: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()


@_ENGINE_OWNER_GATE.policy(
    action=Action.READ,
    subject_type=Article,
    denial_surface=DenialSurface.NULL,
)
def _can_read_owner_only(p: Principal[Actor, str], s: Article) -> Decision:
    if p.actor.is_admin or p.actor.user_id == s.owner_id:
        return ALLOW
    return deny("not_owner")


_ENGINE_ALWAYS_ALLOW: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()


@_ENGINE_ALWAYS_ALLOW.policy(action=Action.READ, subject_type=Article)
def _always_allow(_p: Principal[Actor, str], _s: Article) -> Decision:
    return ALLOW


# Pinned owner UUID -- the loader synthesizes an Article owned by this
# user so the test's "owner" actor can match against it.
_OWNER_UUID: UUID = uuid4()


async def _load_article_from_user(
    source: Any,
    _info: object,
) -> Article | None:
    """Derive a private-profile Article from the parent User source value."""
    if not isinstance(source, _UserGQL):
        return None
    return Article(
        id=_OWNER_UUID,
        owner_id=_OWNER_UUID,
        is_published=False,
    )


async def _load_returns_none(
    _src: Any,
    _info: object,
) -> Article | None:
    """Always-None loader for the not-found-shape test."""
    return None


@strawberry.type
class _UserGQL:
    """Parent type whose source value drives the from-source loader."""

    id: strawberry.ID

    @strawberry.field(
        extensions=[
            policy_guard(
                engine=_ENGINE_OWNER_GATE,
                principal_loader=principal_from_ctx,
                action=Action.READ,
                subject_type=Article,
                load_subject_from_source=_load_article_from_user,
            )
        ],
    )
    async def private_email(self) -> str | None:
        return "secret@example.com"


@strawberry.type
class _LeafGQL:
    """Parent type for the None-loader test."""

    placeholder: str

    @strawberry.field(
        extensions=[
            policy_guard(
                engine=_ENGINE_ALWAYS_ALLOW,
                principal_loader=principal_from_ctx,
                action=Action.READ,
                subject_type=Article,
                load_subject_from_source=_load_returns_none,
            )
        ],
    )
    async def value(self) -> str:
        return "should-not-appear"


@strawberry.type
class _Query:
    @strawberry.field
    async def user(self) -> _UserGQL:
        return _UserGQL(id=strawberry.ID(str(_OWNER_UUID)))

    @strawberry.field
    async def leaf(self) -> _LeafGQL:
        return _LeafGQL(placeholder="p")


_SCHEMA = strawberry.Schema(query=_Query)


class TestLoadSubjectFromSource:
    def test_owner_sees_field(self) -> None:
        ctx = make_ctx(Actor(user_id=_OWNER_UUID, is_admin=False))
        result = asyncio.run(
            _SCHEMA.execute(
                "{ user { id privateEmail } }",
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        data = result.data
        # narrow: data is non-None when errors is None
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["user"]["privateEmail"]).is_equal_to("secret@example.com")

    def test_stranger_gets_null_field(self) -> None:
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        result = asyncio.run(
            _SCHEMA.execute(
                "{ user { id privateEmail } }",
                context_value=ctx,
            )
        )
        # NULL denial: field masked, no top-level error.
        assert_that(result.errors).is_none()
        data = result.data
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["user"]["privateEmail"]).is_none()

    def test_from_source_loader_returning_none_yields_resource_not_found(
        self,
    ) -> None:
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=False))
        result = asyncio.run(_SCHEMA.execute("{ leaf { value } }", context_value=ctx))
        # ResourceNotFound surfaces as a GraphQL error.
        assert_that(result.errors).is_not_none()
