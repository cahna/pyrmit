"""``decide`` logs policy-body exceptions at WARNING, not DEBUG.

A policy that raises is a bug in application code (or an unexpected
runtime failure inside a policy body) -- the engine still converts it to
a safe deny (``policy_error``), but that conversion should be loud enough
to show up in default-configured logs, not require opting into DEBUG.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

import pytest
from assertpy import assert_that

from pyrmit.core.decision import Decision
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestPolicyErrorLogging:
    def test_raising_policy_logs_exactly_one_warning(self, caplog: pytest.LogCaptureFixture) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _broken(_p: object, _s: _Subject) -> Decision:
            raise RuntimeError("boom")

        with caplog.at_level(logging.DEBUG, logger="pyrmit.core.engine"):
            engine.decide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )

        engine_records = [r for r in caplog.records if r.name == "pyrmit.core.engine"]
        warning_records = [r for r in engine_records if r.levelno == logging.WARNING]
        debug_records = [r for r in engine_records if r.levelno == logging.DEBUG]

        assert_that(warning_records).is_length(1)
        assert_that(debug_records).is_length(0)
        assert_that(warning_records[0].getMessage()).contains("policy_error")
