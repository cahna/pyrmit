"""``policy_guard`` on ``@strawberry.subscription``: decide before the stream.

A subscription resolver is an async generator, so calling it returns an
async-generator object rather than an awaitable. The pre-resolution guard
must make its ALLOW/deny decision BEFORE the stream starts and hand the
generator back untouched when allowed; a deny terminates the subscription
with an error and zero ticks. Post-resolution guards cannot decide until
after the stream is produced, so they are refused on subscriptions exactly
as they are on mutations.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import strawberry
from assertpy import assert_that
from strawberry.types import ExecutionResult

from pyrmit import ALLOW, Decision, DenialSurface, Entitlements, PolicyEngine, Principal, deny
from pyrmit.adapters.strawberry import PolicyGuardFactory
from pyrmit.adapters.strawberry.exceptions import PermissionDenied


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


def _engine() -> PolicyEngine[Principal[str], Action, Doc]:
    engine: PolicyEngine[Principal[str], Action, Doc] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Doc)
    def _read(_principal: Principal[str], doc: Doc) -> Decision:
        return ALLOW if doc.public else deny("doc_private")

    return engine


async def _load_doc(_info: Any, kwargs: Mapping[str, Any]) -> Doc | None:
    doc_id = kwargs.get("doc_id")
    if not isinstance(doc_id, int):
        return None
    # doc_id 1 is public; doc_id 2 exists but is private; others are missing.
    return {1: Doc(id=1, public=True), 2: Doc(id=2, public=False)}.get(doc_id)


async def _load_doc_after(_value: Any, _info: Any) -> Doc | None:
    return Doc(id=1, public=True)


def _factory(*, deny_handler: Any = None) -> PolicyGuardFactory[Principal[str], Action, Doc]:
    return PolicyGuardFactory(
        engine=_engine(),
        principal_loader=lambda _info: Principal(actor="u1", entitlements=Entitlements.empty()),
        deny_handler=deny_handler,
    )


def _pre_resolution_schema(factory: PolicyGuardFactory[Principal[str], Action, Doc]) -> strawberry.Schema:
    @strawberry.type
    class Query:
        @strawberry.field
        def ok(self) -> bool:
            return True

    @strawberry.type
    class Subscription:
        @strawberry.subscription(
            extensions=[factory.guard(action=Action.READ, subject_type=Doc, load_subject=_load_doc)]
        )
        async def ticks(self, doc_id: int) -> AsyncGenerator[int, None]:
            del doc_id
            for i in range(3):
                yield i

    return strawberry.Schema(query=Query, subscription=Subscription)


def _post_resolution_schema(
    factory: PolicyGuardFactory[Principal[str], Action, Doc],
    *,
    read_only: bool = True,
) -> strawberry.Schema:
    @strawberry.type
    class Query:
        @strawberry.field
        def ok(self) -> bool:
            return True

    @strawberry.type
    class Subscription:
        @strawberry.subscription(
            extensions=[
                factory.post_resolution_guard(
                    action=Action.READ,
                    subject_type=Doc,
                    load_subject_after=_load_doc_after,
                    read_only=read_only,
                )
            ]
        )
        async def ticks(self, doc_id: int) -> AsyncGenerator[int, None]:
            del doc_id
            for i in range(3):
                yield i

    return strawberry.Schema(query=Query, subscription=Subscription)


def _null_engine() -> PolicyEngine[Principal[str], Action, Doc]:
    """Engine whose READ binding registers a NULL denial surface."""
    engine: PolicyEngine[Principal[str], Action, Doc] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Doc, denial_surface=DenialSurface.NULL)
    def _read(_principal: Principal[str], doc: Doc) -> Decision:
        return ALLOW if doc.public else deny("doc_private")

    return engine


def _null_factory(*, deny_handler: Any = None) -> PolicyGuardFactory[Principal[str], Action, Doc]:
    return PolicyGuardFactory(
        engine=_null_engine(),
        principal_loader=lambda _info: Principal(actor="u1", entitlements=Entitlements.empty()),
        deny_handler=deny_handler,
    )


def _null_subscription_schema(factory: PolicyGuardFactory[Principal[str], Action, Doc]) -> strawberry.Schema:
    """Pre-resolution guard on a subscription, backed by a NULL-surface binding."""

    @strawberry.type
    class Query:
        @strawberry.field
        def ok(self) -> bool:
            return True

    @strawberry.type
    class Subscription:
        @strawberry.subscription(
            extensions=[factory.guard(action=Action.READ, subject_type=Doc, load_subject=_load_doc)]
        )
        async def ticks(self, doc_id: int) -> AsyncGenerator[int, None]:
            del doc_id
            for i in range(3):
                yield i

    return strawberry.Schema(query=Query, subscription=Subscription)


async def _collect(schema: strawberry.Schema, query: str) -> list[ExecutionResult]:
    """Run a subscription and collect every ExecutionResult it yields.

    ``schema.subscribe`` resolves to an async generator of ExecutionResults
    (a pre-start failure is surfaced as a single result carrying errors); we
    also tolerate a bare ExecutionResult for defensiveness across versions.
    """
    maybe = await schema.subscribe(query)
    if hasattr(maybe, "__aiter__"):
        return [result async for result in maybe]
    assert isinstance(maybe, ExecutionResult)  # narrow: bare pre-start result
    return [maybe]


class TestPreResolutionSubscription:
    def test_allowed_subscription_streams_all_values(self) -> None:
        schema = _pre_resolution_schema(_factory())
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 1) }"))
        values = [r.data["ticks"] for r in results if r.data is not None]
        assert_that(values).is_equal_to([0, 1, 2])
        assert_that([r for r in results if r.errors]).is_empty()

    def test_denied_subject_yields_deny_error_and_zero_ticks(self) -> None:
        schema = _pre_resolution_schema(_factory())
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 2) }"))
        errors = [e for r in results for e in (r.errors or [])]
        assert_that(errors).is_not_empty()
        assert_that(str(errors[0].message)).contains("doc_private")
        ticks = [r.data["ticks"] for r in results if r.data]
        assert_that(ticks).is_empty()

    def test_missing_subject_surfaces_not_found(self) -> None:
        schema = _pre_resolution_schema(_factory())
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 999) }"))
        errors = [e for r in results for e in (r.errors or [])]
        assert_that(errors).is_not_empty()
        # The DEFAULT deny_handler normalizes NOT_FOUND to the constant
        # "not_found" so a missing subject is indistinguishable from a
        # NOT_FOUND-surfaced denial (existence concealment). The internal
        # "subject_not_found" reason MUST NOT leak to the client.
        assert_that(str(errors[0].message)).is_equal_to("not_found")
        ticks = [r.data["ticks"] for r in results if r.data]
        assert_that(ticks).is_empty()

    def test_deny_routes_through_custom_deny_handler(self) -> None:
        schema = _pre_resolution_schema(_factory(deny_handler=_host_deny_handler))
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 2) }"))
        originals = [e.original_error for r in results for e in (r.errors or [])]
        assert_that(originals).is_not_empty()
        assert_that(originals[0]).is_instance_of(HostDenied)
        assert isinstance(originals[0], HostDenied)  # narrow: attribute access
        assert_that(originals[0].reason).is_equal_to("doc_private")


class TestPostResolutionSubscriptionBlocked:
    def test_post_resolution_guard_on_subscription_is_blocked(self) -> None:
        # Policy would ALLOW (doc is public), but a post-resolution guard on a
        # subscription is refused before the resolver runs -- zero ticks.
        schema = _post_resolution_schema(_factory())
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 1) }"))
        errors = [e for r in results for e in (r.errors or [])]
        assert_that(errors).is_not_empty()
        assert_that(str(errors[0].message)).contains("post_resolution_guard_on_subscription_blocked")
        ticks = [r.data["ticks"] for r in results if r.data]
        assert_that(ticks).is_empty()

    def test_read_only_false_does_not_opt_out_of_subscription_block(self) -> None:
        # read_only=False is a coherent opt-out for MUTATIONS, but on a
        # subscription a post-resolution guard can NEVER work (the resolver
        # returns a stream, not a value). The refusal must be unconditional:
        # a clean PermissionDenied, not a raw TypeError from awaiting the
        # async generator.
        schema = _post_resolution_schema(_factory(), read_only=False)
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 1) }"))
        errors = [e for r in results for e in (r.errors or [])]
        assert_that(errors).is_not_empty()
        message = str(errors[0].message)
        assert_that(message).contains("post_resolution_guard_on_subscription_blocked")
        assert_that(message).does_not_contain("TypeError")
        originals = [e.original_error for r in results for e in (r.errors or [])]
        assert_that(originals[0]).is_instance_of(PermissionDenied)
        ticks = [r.data["ticks"] for r in results if r.data]
        assert_that(ticks).is_empty()


class TestNullSurfaceSubscriptionDeny:
    def test_null_surface_deny_falls_closed_to_forbidden(self) -> None:
        # A binding registered NULL (for field redaction) also guards a
        # subscription. NULL has no meaning for a stream -- returning None
        # would make graphql-core raise "Subscription field must return
        # AsyncIterable. Received: None". The guard must fall closed to
        # FORBIDDEN and the custom deny_handler must observe that surface.
        schema = _null_subscription_schema(_null_factory(deny_handler=_host_deny_handler))
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 2) }"))
        originals = [e.original_error for r in results for e in (r.errors or [])]
        assert_that(originals).is_not_empty()
        assert_that(originals[0]).is_instance_of(HostDenied)
        assert isinstance(originals[0], HostDenied)  # narrow: attribute access
        assert_that(originals[0].surface).is_equal_to(DenialSurface.FORBIDDEN.value)
        assert_that(originals[0].reason).is_equal_to("doc_private")
        ticks = [r.data["ticks"] for r in results if r.data]
        assert_that(ticks).is_empty()

    def test_null_surface_allow_still_streams(self) -> None:
        # Sanity: the NULL-surfaced binding still opens the stream on ALLOW.
        schema = _null_subscription_schema(_null_factory())
        results = asyncio.run(_collect(schema, "subscription { ticks(docId: 1) }"))
        values = [r.data["ticks"] for r in results if r.data is not None]
        assert_that(values).is_equal_to([0, 1, 2])
        assert_that([r for r in results if r.errors]).is_empty()
