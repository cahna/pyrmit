"""Tests for JsonLinesAuditStore."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

from assertpy import assert_that

from pyrmit.audit.jsonlines import JsonLinesAuditStore
from pyrmit.core.audit import AuditEntry, AuditOutcome


def _entry(seq: int) -> AuditEntry:
    return AuditEntry(
        id=f"id-{seq:04d}",
        timestamp=datetime(2026, 5, 17, tzinfo=UTC),
        outcome=AuditOutcome.DENIED,
        action="read",
        subject_type="Article",
        subject_id=f"a-{seq}",
        actor_id=f"u-{seq}",
        reason="x",
    )


class TestJsonLinesAuditStore:
    def test_appends_one_line_per_entry(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        store = JsonLinesAuditStore(path=path)
        for i in range(3):
            asyncio.run(store.write(_entry(i)))
        asyncio.run(store.aclose())

        text = path.read_text(encoding="utf-8")
        lines = text.strip().split("\n")
        assert_that(lines).is_length(3)
        parsed = [json.loads(line) for line in lines]
        assert_that(parsed[0]["id"]).is_equal_to("id-0000")
        assert_that(parsed[2]["id"]).is_equal_to("id-0002")

    def test_creates_file_on_first_write(self, tmp_path: Path) -> None:
        path = tmp_path / "fresh.jsonl"
        assert_that(path.exists()).is_false()
        store = JsonLinesAuditStore(path=path)
        asyncio.run(store.write(_entry(1)))
        asyncio.run(store.aclose())
        assert_that(path.exists()).is_true()

    def test_serialized_form_is_valid_json(self, tmp_path: Path) -> None:
        path = tmp_path / "audit.jsonl"
        store = JsonLinesAuditStore(path=path)
        asyncio.run(store.write(_entry(0)))
        asyncio.run(store.aclose())
        line = path.read_text(encoding="utf-8").strip().split("\n")[0]
        loaded = json.loads(line)
        assert_that(loaded["outcome"]).is_equal_to("denied")
        assert_that(loaded["action"]).is_equal_to("read")
        assert_that(loaded["subject_id"]).is_equal_to("a-0")
