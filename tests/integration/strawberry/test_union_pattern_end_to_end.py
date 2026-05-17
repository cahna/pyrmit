"""Union subject-type pattern end-to-end through the Strawberry adapter.

Closes an integration gap: prior tests verify
registration-time behavior of ``subject_base`` but no test wires a
PEP 695 union type into an actual Strawberry schema and exercises both
subject types through ``policy_guard``. This file does exactly that:

1. Builds a ``PolicyEngine[Principal[Actor, str], Action, AppSubject]``
   over ``type AppSubject = MatchSubject | ClubSubject``.
2. Configures ``subject_base=AppSubject`` so the runtime guard is on.
3. Registers two policies (one per subject type) and one subject-id
   resolver per subject type.
4. Wires both into a Strawberry schema with ``policy_guard``-protected
   fields, one per subject type.
5. Verifies that decisions, audit, and denial-surface handling all work
   correctly across both subject types in a single shared engine.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import strawberry
from assertpy import assert_that
from strawberry.types import Info

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.errors import InvalidSubjectTypeError
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class MatchSubject:
    match_id: UUID
    owner_id: UUID
    is_published: bool


@dataclass(frozen=True)
class ClubSubject:
    club_id: UUID
    name: str
    is_active: bool


# Union pattern: PEP 695 union alias.
type AppSubject = MatchSubject | ClubSubject


# ----------------------------------------------------------- engine + bindings

_AUDIT_STORE = InMemoryAuditStore(capacity=16)

_ENGINE: PolicyEngine[Principal[Actor, str], Action, AppSubject] = PolicyEngine(
    audit=_AUDIT_STORE,
    audit_allows=True,
    actor_id=lambda p: str(p.actor.user_id),
    subject_base=AppSubject,  # PEP 695 auto-extract
)


@_ENGINE.policy(
    action=Action.READ,
    subject_type=MatchSubject,
    denial_surface=DenialSurface.FORBIDDEN,
)
def _read_match(p: Principal[Actor, str], s: MatchSubject) -> Decision:
    if s.is_published or p.actor.user_id == s.owner_id:
        return ALLOW
    return deny("match_unpublished")


@_ENGINE.policy(
    action=Action.READ,
    subject_type=ClubSubject,
    denial_surface=DenialSurface.NULL,
)
def _read_club(_p: Principal[Actor, str], s: ClubSubject) -> Decision:
    if not s.is_active:
        return deny("club_inactive")
    return ALLOW


_ENGINE.register_subject_id(
    subject_type=MatchSubject,
    resolver=lambda s: str(s.match_id),
)
_ENGINE.register_subject_id(
    subject_type=ClubSubject,
    resolver=lambda s: str(s.club_id),
)


# ----------------------------------------------------------- fixture data + loaders

_OWNER = UUID(int=0xA)

_MATCHES: dict[UUID, MatchSubject] = {}
_CLUBS: dict[UUID, ClubSubject] = {}

PUBLISHED_MATCH = MatchSubject(
    match_id=uuid4(),
    owner_id=_OWNER,
    is_published=True,
)
UNPUBLISHED_MATCH = MatchSubject(
    match_id=uuid4(),
    owner_id=_OWNER,
    is_published=False,
)
ACTIVE_CLUB = ClubSubject(club_id=uuid4(), name="active", is_active=True)
INACTIVE_CLUB = ClubSubject(club_id=uuid4(), name="inactive", is_active=False)

for m in (PUBLISHED_MATCH, UNPUBLISHED_MATCH):
    _MATCHES[m.match_id] = m
for c in (ACTIVE_CLUB, INACTIVE_CLUB):
    _CLUBS[c.club_id] = c


async def _load_match(_info: Info[Any, Any], kwargs: Mapping[str, Any]) -> MatchSubject | None:
    raw = kwargs.get("match_id")
    if raw is None:
        return None
    try:
        return _MATCHES.get(UUID(str(raw)))
    except (ValueError, TypeError):
        return None


async def _load_club(_info: Info[Any, Any], kwargs: Mapping[str, Any]) -> ClubSubject | None:
    raw = kwargs.get("club_id")
    if raw is None:
        return None
    try:
        return _CLUBS.get(UUID(str(raw)))
    except (ValueError, TypeError):
        return None


# ----------------------------------------------------------- Strawberry schema


class _Ctx:
    def __init__(self, actor_id: UUID) -> None:
        self.actor = Actor(user_id=actor_id)
        self.principal_loader_calls = 0


def _principal_from_ctx(info: Info[Any, Any]) -> Principal[Actor, str]:
    ctx: _Ctx = info.context
    ctx.principal_loader_calls += 1
    return Principal(actor=ctx.actor, entitlements=Entitlements.empty())


@strawberry.type
class _Query:
    @strawberry.field(
        extensions=[
            policy_guard(
                engine=_ENGINE,
                principal_loader=_principal_from_ctx,
                action=Action.READ,
                subject_type=MatchSubject,
                load_subject=_load_match,
            )
        ],
    )
    async def match_title(self, match_id: strawberry.ID) -> str:
        del match_id
        return "the-match-title"

    @strawberry.field(
        extensions=[
            policy_guard(
                engine=_ENGINE,
                principal_loader=_principal_from_ctx,
                action=Action.READ,
                subject_type=ClubSubject,
                load_subject=_load_club,
            )
        ],
    )
    async def club_name(self, club_id: strawberry.ID) -> str | None:
        return "the-club-name"


_SCHEMA = strawberry.Schema(query=_Query)


# ----------------------------------------------------------- tests


class TestPatternAEndToEnd:
    def setup_method(self) -> None:
        """Clear audit between tests to keep assertions independent."""
        _AUDIT_STORE.clear()

    def test_published_match_allowed_via_pattern_a_engine(self) -> None:
        ctx = _Ctx(actor_id=uuid4())  # stranger
        result = asyncio.run(
            _SCHEMA.execute(
                f'{{ matchTitle(matchId: "{PUBLISHED_MATCH.match_id}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        data = result.data
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["matchTitle"]).is_equal_to("the-match-title")

        # Audit was emitted -- the SAME engine handles both subject types.
        entries = _AUDIT_STORE.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].subject_type).is_equal_to("MatchSubject")
        assert_that(entries[0].subject_id).is_equal_to(
            str(PUBLISHED_MATCH.match_id),
        )
        assert_that(entries[0].outcome.value).is_equal_to("allowed")

    def test_unpublished_match_denied_forbidden(self) -> None:
        ctx = _Ctx(actor_id=uuid4())  # stranger; not the owner
        result = asyncio.run(
            _SCHEMA.execute(
                f'{{ matchTitle(matchId: "{UNPUBLISHED_MATCH.match_id}") }}',
                context_value=ctx,
            )
        )
        # FORBIDDEN denial: GraphQL error returned.
        assert_that(result.errors).is_not_none()

    def test_active_club_allowed(self) -> None:
        ctx = _Ctx(actor_id=uuid4())
        result = asyncio.run(
            _SCHEMA.execute(
                f'{{ clubName(clubId: "{ACTIVE_CLUB.club_id}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        data = result.data
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["clubName"]).is_equal_to("the-club-name")

        entries = _AUDIT_STORE.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].subject_type).is_equal_to("ClubSubject")
        assert_that(entries[0].subject_id).is_equal_to(
            str(ACTIVE_CLUB.club_id),
        )

    def test_inactive_club_denied_null(self) -> None:
        ctx = _Ctx(actor_id=uuid4())
        result = asyncio.run(
            _SCHEMA.execute(
                f'{{ clubName(clubId: "{INACTIVE_CLUB.club_id}") }}',
                context_value=ctx,
            )
        )
        # NULL denial: no top-level error, field masked to null.
        assert_that(result.errors).is_none()
        data = result.data
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["clubName"]).is_none()

        # Audit recorded the deny with the correct subject_type.
        entries = _AUDIT_STORE.entries()
        denials = [e for e in entries if e.outcome.value == "denied"]
        assert_that(denials).is_length(1)
        assert_that(denials[0].subject_type).is_equal_to("ClubSubject")
        assert_that(denials[0].reason).is_equal_to("club_inactive")

    def test_both_subject_types_in_one_query(self) -> None:
        """A single GraphQL operation that decides against BOTH subject
        types reuses the same engine; the principal is cached once.
        """
        ctx = _Ctx(actor_id=uuid4())
        result = asyncio.run(
            _SCHEMA.execute(
                f'''{{
                    matchTitle(matchId: "{PUBLISHED_MATCH.match_id}")
                    clubName(clubId: "{ACTIVE_CLUB.club_id}")
                }}''',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()
        data = result.data
        assert data is not None  # narrow: type-narrow Optional payload
        assert_that(data["matchTitle"]).is_equal_to("the-match-title")
        assert_that(data["clubName"]).is_equal_to("the-club-name")
        # Principal cached once across the two guarded fields.
        assert_that(ctx.principal_loader_calls).is_equal_to(1)

    def test_orphan_subject_type_rejected_at_registration(self) -> None:
        """The runtime guard refuses to register a policy for a type
        that is NOT in the subject union, BEFORE any query runs.
        """
        # We use a separate engine here to avoid corrupting the
        # module-level _ENGINE used by the other tests.
        local_engine: PolicyEngine[Principal[Actor, str], Action, AppSubject] = PolicyEngine(subject_base=AppSubject)

        @dataclass(frozen=True)
        class _NotASubject:
            payload: str

        try:

            @local_engine.policy(action=Action.READ, subject_type=_NotASubject)
            def _orphan(
                _p: Principal[Actor, str],
                _s: _NotASubject,
            ) -> Decision:
                return ALLOW

        except InvalidSubjectTypeError as err:
            assert_that(err.subject_type).is_equal_to("_NotASubject")
            # The expected-base string lists BOTH union members.
            assert_that(err.expected_base).contains("MatchSubject")
            assert_that(err.expected_base).contains("ClubSubject")
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError on orphan registration").is_true()
