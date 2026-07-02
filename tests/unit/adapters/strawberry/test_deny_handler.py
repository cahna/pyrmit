"""``deny_handler`` lets the host raise its own exception taxonomy.

By default ``policy_guard`` raises pyrmit's own ``PermissionDenied`` /
``ResourceNotFound``. Host applications that already have an established
error taxonomy (e.g. GraphQL error types with ``extensions.code``) need a
hook to translate a denial into their own exception instead. This module
verifies the hook fires for both FORBIDDEN denials and the missing-subject
NOT_FOUND path, and that it is threaded through ``PolicyGuardFactory``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import strawberry
from assertpy import assert_that

from pyrmit import ALLOW, Decision, DenialSurface, Entitlements, PolicyEngine, Principal, deny
from pyrmit.adapters.strawberry import PolicyGuardFactory
from pyrmit.adapters.strawberry.guard import default_deny_handler


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Doc:
    id: int
    public: bool


class HostDenied(Exception):  # noqa: N818  -- matches GraphQL ecosystem naming
    """Stand-in for a host application's own denial exception taxonomy."""

    def __init__(self, reason: str, surface: str) -> None:
        super().__init__(reason)
        self.reason = reason
        self.surface = surface


def _host_deny_handler(decision: Decision, surface: DenialSurface) -> Exception:
    return HostDenied(decision.reason or "denied", surface.value)


def _build_schema() -> strawberry.Schema:
    engine: PolicyEngine[Principal[str], Action, Doc] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Doc)
    def _read(_principal: Principal[str], doc: Doc) -> Decision:
        return ALLOW if doc.public else deny("doc_private")

    factory = PolicyGuardFactory(
        engine=engine,
        principal_loader=lambda _info: Principal(actor="u1", entitlements=Entitlements.empty()),
        deny_handler=_host_deny_handler,
    )

    async def load_doc(_info: Any, kwargs: Mapping[str, Any]) -> Doc | None:
        doc_id = kwargs.get("doc_id")
        if not isinstance(doc_id, int):
            return None
        return {1: Doc(id=1, public=False)}.get(doc_id)

    @strawberry.type
    class Query:
        @strawberry.field(extensions=[factory.guard(action=Action.READ, subject_type=Doc, load_subject=load_doc)])
        async def doc(self, doc_id: int) -> str:
            del doc_id
            return "content"

    return strawberry.Schema(query=Query)


class TestDenyHandler:
    def test_denial_raises_host_exception(self) -> None:
        result = asyncio.run(_build_schema().execute("{ doc(docId: 1) }"))
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        original = result.errors[0].original_error
        assert_that(original).is_instance_of(HostDenied)
        assert isinstance(original, HostDenied)  # narrow: mypy needs this for attribute access below
        assert_that(original.reason).is_equal_to("doc_private")

    def test_missing_subject_routes_through_handler_as_not_found(self) -> None:
        result = asyncio.run(_build_schema().execute("{ doc(docId: 999) }"))
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        original = result.errors[0].original_error
        assert_that(original).is_instance_of(HostDenied)
        assert isinstance(original, HostDenied)  # narrow: mypy needs this for attribute access below
        # A CUSTOM handler still receives the real Decision/reason -- only the
        # DEFAULT handler normalizes the outward message.
        assert_that(original.reason).is_equal_to("subject_not_found")
        assert_that(original.surface).is_equal_to("not_found")


class TestDefaultHandlerConcealsExistence:
    """The DEFAULT handler must make restricted-vs-missing indistinguishable.

    A NOT_FOUND-surfaced DENIAL (a real, restricted resource) and a genuine
    ABSENCE (no such resource) must both emit the constant "not_found" so a
    client cannot distinguish the two via the error message.
    """

    def test_denial_and_absence_emit_identical_constant(self) -> None:
        denial = default_deny_handler(
            deny("doc_private"),
            DenialSurface.NOT_FOUND,
        )
        absence = default_deny_handler(
            Decision(allowed=False, reason="subject_not_found"),
            DenialSurface.NOT_FOUND,
        )
        post_absence = default_deny_handler(
            Decision(allowed=False, reason="subject_post_resolution_missing"),
            DenialSurface.NOT_FOUND,
        )
        assert_that(str(denial)).is_equal_to("not_found")
        assert_that(str(absence)).is_equal_to("not_found")
        assert_that(str(post_absence)).is_equal_to("not_found")

    def test_end_to_end_denial_and_absence_are_indistinguishable(self) -> None:
        engine: PolicyEngine[Principal[str], Action, Doc] = PolicyEngine()

        @engine.policy(action=Action.READ, subject_type=Doc, denial_surface=DenialSurface.NOT_FOUND)
        def _read(_p: Principal[str], doc: Doc) -> Decision:
            return ALLOW if doc.public else deny("doc_private")

        factory = PolicyGuardFactory(
            engine=engine,
            principal_loader=lambda _info: Principal(actor="u1", entitlements=Entitlements.empty()),
        )

        async def load_doc(_info: Any, kwargs: Mapping[str, Any]) -> Doc | None:
            doc_id = kwargs.get("doc_id")
            if not isinstance(doc_id, int):
                return None
            return {1: Doc(id=1, public=False)}.get(doc_id)

        @strawberry.type
        class Query:
            @strawberry.field(extensions=[factory.guard(action=Action.READ, subject_type=Doc, load_subject=load_doc)])
            async def doc(self, doc_id: int) -> str:
                del doc_id
                return "content"

        schema = strawberry.Schema(query=Query)
        restricted = asyncio.run(schema.execute("{ doc(docId: 1) }"))  # exists, denied NOT_FOUND
        missing = asyncio.run(schema.execute("{ doc(docId: 999) }"))  # absent
        assert restricted.errors is not None and missing.errors is not None  # narrow
        assert_that(str(restricted.errors[0].message)).is_equal_to("not_found")
        assert_that(str(missing.errors[0].message)).is_equal_to("not_found")
