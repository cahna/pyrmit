"""Tests for pyrmit.testing.matrix.policy_matrix."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.testing.matrix import policy_matrix


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class _Subject:
    id: int
    is_open: bool


class TestPolicyMatrix:
    def test_matrix_enumerates_all_combinations(self) -> None:
        engine: PolicyEngine[str, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _read(_p: str, s: _Subject) -> Decision:
            return ALLOW if s.is_open else deny("closed")

        @engine.policy(action=_Action.WRITE, subject_type=_Subject)
        def _write(_p: str, _s: _Subject) -> Decision:
            return deny("never")

        principals = ["alice", "bob"]
        actions = [_Action.READ, _Action.WRITE]
        subjects = [_Subject(id=1, is_open=True), _Subject(id=2, is_open=False)]

        matrix = policy_matrix(
            engine=engine,
            principals=principals,
            actions=actions,
            subjects=subjects,
        )
        assert_that(matrix).is_length(2 * 2 * 2)
        # Allowed only when action=READ AND subject.is_open
        for (p, a, s_repr), decision in matrix.items():
            if a == _Action.READ.value and "is_open=True" in s_repr:
                assert_that(decision.allowed).described_as(f"{p}/{a}/{s_repr}").is_true()
            else:
                assert_that(decision.allowed).described_as(f"{p}/{a}/{s_repr}").is_false()
