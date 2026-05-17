"""Regression test: union and marker-base subject-type patterns.

These patterns are the documented user-facing subject-type
parameterization recipes. They MUST compile under mypy --strict and
MUST work at runtime. A prior refactor dropped the bounded ``ST: SubjectT``
TypeVar from ``policy()`` and silently broke both patterns; no existing
test caught the regression because every other test used
``PolicyEngine[..., <SingleConcreteSubject>]``. This file closes that gap.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Actor:
    user_id: UUID


# ----------------------------------------------------------- union pattern


@dataclass(frozen=True)
class _MatchSubject:
    match_id: UUID


@dataclass(frozen=True)
class _ClubSubject:
    club_id: UUID
    is_active: bool


type _AppSubject = _MatchSubject | _ClubSubject


class TestPatternAUnion:
    def test_engine_parameterized_over_union_compiles_and_runs(self) -> None:
        engine: PolicyEngine[Principal[_Actor, str], _Action, _AppSubject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _read_match(
            _p: Principal[_Actor, str],
            _s: _MatchSubject,
        ) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.READ, subject_type=_ClubSubject)
        def _read_club(
            _p: Principal[_Actor, str],
            s: _ClubSubject,
        ) -> Decision:
            return ALLOW if s.is_active else deny("club_inactive")

        principal: Principal[_Actor, str] = Principal(
            actor=_Actor(user_id=uuid4()),
            entitlements=Entitlements.empty(),
        )

        # Both subject types dispatch to their respective bindings.
        match_decision = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_MatchSubject(match_id=uuid4()),
        )
        assert_that(match_decision.allowed).is_true()

        active_club = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_ClubSubject(club_id=uuid4(), is_active=True),
        )
        assert_that(active_club.allowed).is_true()

        inactive_club = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_ClubSubject(club_id=uuid4(), is_active=False),
        )
        assert_that(inactive_club.allowed).is_false()
        assert_that(inactive_club.reason).is_equal_to("club_inactive")


# ----------------------------------------------------------- marker-base pattern


@dataclass(frozen=True)
class _Subject:
    """Marker base class. Subjects inherit but add no shared fields."""


@dataclass(frozen=True)
class _Article(_Subject):
    article_id: UUID
    is_published: bool


@dataclass(frozen=True)
class _Comment(_Subject):
    comment_id: UUID


class TestPatternBMarkerBase:
    def test_engine_parameterized_over_marker_base_compiles_and_runs(
        self,
    ) -> None:
        engine: PolicyEngine[Principal[_Actor, str], _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Article)
        def _read_article(
            _p: Principal[_Actor, str],
            s: _Article,
        ) -> Decision:
            return ALLOW if s.is_published else deny("draft")

        @engine.policy(action=_Action.READ, subject_type=_Comment)
        def _read_comment(
            _p: Principal[_Actor, str],
            _s: _Comment,
        ) -> Decision:
            return ALLOW

        principal: Principal[_Actor, str] = Principal(
            actor=_Actor(user_id=uuid4()),
            entitlements=Entitlements.empty(),
        )

        published = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_Article(article_id=uuid4(), is_published=True),
        )
        assert_that(published.allowed).is_true()

        draft = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_Article(article_id=uuid4(), is_published=False),
        )
        assert_that(draft.allowed).is_false()
        assert_that(draft.reason).is_equal_to("draft")

        comment_ok = engine.decide(
            principal=principal,
            action=_Action.READ,
            subject=_Comment(comment_id=uuid4()),
        )
        assert_that(comment_ok.allowed).is_true()
