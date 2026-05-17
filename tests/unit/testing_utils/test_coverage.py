"""Tests for pyrmit.testing.coverage helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.testing.coverage import assert_policy_registered


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestAssertPolicyRegistered:
    def test_passes_when_registered(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        assert_policy_registered(engine=engine, action=_Action.READ, subject_type=_Subject)

    def test_raises_when_not_registered(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        try:
            assert_policy_registered(engine=engine, action=_Action.WRITE, subject_type=_Subject)
        except AssertionError:
            return
        assert_that(False).described_as("expected AssertionError").is_true()
