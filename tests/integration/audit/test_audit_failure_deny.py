"""audit_failure_mode='deny': failure converts decision to audit_unavailable."""

from __future__ import annotations

import asyncio
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
    async def write(self, entry: AuditEntry) -> None:
        del entry
        raise RuntimeError("store down")


class TestAuditFailureDeny:
    def test_store_failure_returns_audit_unavailable_deny(self) -> None:
        store: AuditStore = _RaisingStore()
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_failure_mode="deny",
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return deny("real_reason")

        d = asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )

        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("audit_unavailable")
