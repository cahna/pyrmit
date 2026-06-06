"""Tests for InMemoryAuditStore."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from assertpy import assert_that

from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.audit import AuditEntry, AuditOutcome


def _entry(seq: int) -> AuditEntry:
    return AuditEntry(
        id=f"id-{seq:04d}",
        timestamp=datetime(2026, 5, 17, tzinfo=UTC),
        outcome=AuditOutcome.DENIED,
        action="read",
        subject_type="Article",
        reason="x",
    )


class TestInMemoryAuditStore:
    def test_stores_entries_in_order(self) -> None:
        store = InMemoryAuditStore(capacity=10)
        for i in range(5):
            asyncio.run(store.write(_entry(i)))
        items = store.entries()
        assert_that(items).is_length(5)
        assert_that(items[0].id).is_equal_to("id-0000")
        assert_that(items[4].id).is_equal_to("id-0004")

    def test_capacity_evicts_oldest(self) -> None:
        store = InMemoryAuditStore(capacity=3)
        for i in range(7):
            asyncio.run(store.write(_entry(i)))
        items = store.entries()
        assert_that(items).is_length(3)
        # Oldest 4 evicted; we retain 4, 5, 6.
        assert_that([e.id for e in items]).is_equal_to([
            "id-0004",
            "id-0005",
            "id-0006",
        ])

    def test_entries_returns_snapshot_tuple(self) -> None:
        store = InMemoryAuditStore(capacity=10)
        asyncio.run(store.write(_entry(0)))
        snap = store.entries()
        # Mutating after snapshot must not affect the returned tuple.
        asyncio.run(store.write(_entry(1)))
        assert_that(snap).is_length(1)
        assert_that(snap[0].id).is_equal_to("id-0000")

    def test_clear(self) -> None:
        store = InMemoryAuditStore(capacity=10)
        asyncio.run(store.write(_entry(0)))
        store.clear()
        assert_that(store.entries()).is_empty()
