"""Tests for pyrmit.testing.assertions."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.testing.assertions import assert_allowed, assert_denied


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


def _engine_allow() -> PolicyEngine[object, _Action, _Subject]:
    engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

    @engine.policy(action=_Action.READ, subject_type=_Subject)
    def _pol(_p: object, _s: _Subject) -> Decision:
        return ALLOW

    return engine


def _engine_deny(reason: str) -> PolicyEngine[object, _Action, _Subject]:
    engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

    @engine.policy(action=_Action.READ, subject_type=_Subject)
    def _pol(_p: object, _s: _Subject) -> Decision:
        return deny(reason)

    return engine


class TestAssertAllowed:
    def test_passes_when_decision_is_allow(self) -> None:
        engine = _engine_allow()
        assert_allowed(engine, principal=object(), action=_Action.READ, subject=_Subject(id=1))

    def test_raises_when_decision_is_deny(self) -> None:
        engine = _engine_deny("nope")
        try:
            assert_allowed(
                engine,
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        except AssertionError:
            return
        assert_that(False).described_as("expected AssertionError").is_true()


class TestAssertDenied:
    def test_passes_when_decision_is_deny_without_reason_check(self) -> None:
        engine = _engine_deny("nope")
        assert_denied(engine, principal=object(), action=_Action.READ, subject=_Subject(id=1))

    def test_passes_when_reason_matches(self) -> None:
        engine = _engine_deny("nope")
        assert_denied(
            engine,
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1),
            reason="nope",
        )

    def test_raises_when_reason_mismatches(self) -> None:
        engine = _engine_deny("actual")
        try:
            assert_denied(
                engine,
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
                reason="expected",
            )
        except AssertionError:
            return
        assert_that(False).described_as("expected AssertionError").is_true()

    def test_raises_when_decision_is_allow(self) -> None:
        engine = _engine_allow()
        try:
            assert_denied(
                engine,
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        except AssertionError:
            return
        assert_that(False).described_as("expected AssertionError").is_true()
