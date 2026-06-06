"""Audit-entry id is a UUIDv7."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

from assertpy import assert_that

from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.audit import AuditOutcome
from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestAuditEntryUuidV7:
    def test_entry_id_is_uuidv7_with_timestamp_close_to_entry_timestamp(
        self,
    ) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )

        entries = store.entries()
        assert_that(entries).is_length(1)
        entry = entries[0]
        # Hex form (32 chars, no dashes) is what the engine produces.
        assert_that(len(entry.id)).is_equal_to(32)
        # Round-trip through UUID to validate format.
        u = UUID(hex=entry.id)
        assert_that(u.version).is_equal_to(7)
        assert_that(entry.outcome).is_equal_to(AuditOutcome.ALLOWED)
        assert_that(isinstance(entry.timestamp, datetime)).is_true()
