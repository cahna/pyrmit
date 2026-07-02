"""``denial_surface`` per-guard override.

A binding registers its policy with one ``denial_surface`` (the default
used everywhere the binding is guarded). Some fields need a different
surface for that one attachment point -- e.g. a binding registered
FORBIDDEN everywhere, but one particular field wants to redact to
``null`` instead of raising. ``policy_guard(..., denial_surface=...)``
(and the factory equivalents) let a single guard attachment override the
binding's surface without touching the registration.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

import strawberry
from assertpy import assert_that

from pyrmit import ALLOW, Decision, DenialSurface, Entitlements, PolicyEngine, Principal, deny
from pyrmit.adapters.strawberry import PolicyGuardFactory


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Doc:
    id: int
    public: bool


def _engine_with_forbidden_binding() -> PolicyEngine[Principal[str], Action, Doc]:
    engine: PolicyEngine[Principal[str], Action, Doc] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Doc, denial_surface=DenialSurface.FORBIDDEN)
    def _read(_principal: Principal[str], doc: Doc) -> Decision:
        return ALLOW if doc.public else deny("doc_private")

    return engine


def _factory(engine: PolicyEngine[Principal[str], Action, Doc]) -> PolicyGuardFactory[Principal[str], Action, Doc]:
    return PolicyGuardFactory(
        engine=engine,
        principal_loader=lambda _info: Principal(actor="u1", entitlements=Entitlements.empty()),
    )


class TestNullOverride:
    """Overriding a FORBIDDEN binding to NULL for a single field."""

    def _build_schema(self) -> strawberry.Schema:
        factory = _factory(_engine_with_forbidden_binding())

        async def load_doc(_source: object, _info: object) -> Doc:
            del _source, _info
            return Doc(id=1, public=False)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
                        action=Action.READ,
                        subject_type=Doc,
                        load_subject_from_source=load_doc,
                        denial_surface=DenialSurface.NULL,
                    )
                ]
            )
            async def doc(self) -> str | None:
                return "content"

        return strawberry.Schema(query=Query)

    def test_denied_field_resolves_to_null_with_no_errors(self) -> None:
        result = asyncio.run(self._build_schema().execute("{ doc }"))
        assert_that(result.errors).is_none()
        assert_that(result.data).is_equal_to({"doc": None})


class TestNotFoundOverride:
    """Overriding a FORBIDDEN binding to NOT_FOUND routes through deny_handler."""

    def _build_schema(self) -> strawberry.Schema:
        factory = _factory(_engine_with_forbidden_binding())

        async def load_doc(_source: object, _info: object) -> Doc:
            del _source, _info
            return Doc(id=1, public=False)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
                        action=Action.READ,
                        subject_type=Doc,
                        load_subject_from_source=load_doc,
                        denial_surface=DenialSurface.NOT_FOUND,
                    )
                ]
            )
            async def doc(self) -> str | None:
                return "content"

        return strawberry.Schema(query=Query)

    def test_denied_field_raises_not_found(self) -> None:
        from pyrmit.adapters.strawberry import ResourceNotFound

        result = asyncio.run(self._build_schema().execute("{ doc }"))
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        original = result.errors[0].original_error
        assert_that(original).is_instance_of(ResourceNotFound)


class TestNoOverridePreservesBindingSurface:
    """Omitting ``denial_surface`` preserves the binding's own surface."""

    def _build_schema(self) -> strawberry.Schema:
        factory = _factory(_engine_with_forbidden_binding())

        async def load_doc(_source: object, _info: object) -> Doc:
            del _source, _info
            return Doc(id=1, public=False)

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    factory.guard(
                        action=Action.READ,
                        subject_type=Doc,
                        load_subject_from_source=load_doc,
                    )
                ]
            )
            async def doc(self) -> str | None:
                return "content"

        return strawberry.Schema(query=Query)

    def test_denied_field_raises_permission_denied(self) -> None:
        from pyrmit.adapters.strawberry import PermissionDenied

        result = asyncio.run(self._build_schema().execute("{ doc }"))
        assert_that(result.errors).is_not_none()
        assert result.errors is not None  # narrow: type-narrow Optional errors
        original = result.errors[0].original_error
        assert_that(original).is_instance_of(PermissionDenied)
