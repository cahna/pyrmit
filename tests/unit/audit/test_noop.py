"""Tests for NoopAuditStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from assertpy import assert_that

from pyrmit.audit.noop import NoopAuditStore
from pyrmit.core.audit import AuditEntry, AuditOutcome


class TestNoopAuditStore:
    def test_write_returns_none(self) -> None:
        store = NoopAuditStore()
        entry = AuditEntry(
            id="id-1",
            timestamp=datetime(2026, 5, 17, tzinfo=UTC),
            outcome=AuditOutcome.ALLOWED,
            action="read",
            subject_type="Article",
        )
        result = asyncio.run(store.write(entry))
        assert_that(result).is_none()

    def test_no_state_retained(self) -> None:
        store = NoopAuditStore()
        # No public retrieval API exists; the store has __slots__ = ().
        assert_that(hasattr(store, "entries")).is_false()
