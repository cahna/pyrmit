"""audit_failure_mode='log': failure logged, decision unchanged."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.audit import AuditEntry, AuditStore
from pyrmit.core.decision import Decision, deny
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class _RaisingStore:
    """An AuditStore whose write() always raises."""

    async def write(self, entry: AuditEntry) -> None:
        del entry
        raise RuntimeError("store down")


class TestAuditFailureLog:
    def test_decision_proceeds_unchanged_under_log_mode(
        self,
        caplog: object,
    ) -> None:
        from _pytest.logging import LogCaptureFixture

        assert isinstance(caplog, LogCaptureFixture)  # narrow: pytest fixture

        store: AuditStore = _RaisingStore()
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_failure_mode="log",
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return deny("real_reason")

        with caplog.at_level(logging.WARNING, logger="pyrmit.core.engine"):
            d = asyncio.run(
                engine.adecide(
                    principal=object(),
                    action=_Action.READ,
                    subject=_Subject(id=1),
                )
            )

        # Decision MUST be the original deny, NOT audit_unavailable.
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("real_reason")
        # Warning was emitted.
        warning_records = [r for r in caplog.records if r.levelname == "WARNING"]
        assert_that(warning_records).is_not_empty()
