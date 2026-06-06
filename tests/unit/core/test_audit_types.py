"""Unit tests for `pyrmit.core.audit` types."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import MappingProxyType

from assertpy import assert_that

from pyrmit.core.audit import AuditEntry, AuditOutcome, AuditStore


class TestAuditOutcome:
    def test_enum_values(self) -> None:
        assert_that(AuditOutcome.ALLOWED.value).is_equal_to("allowed")
        assert_that(AuditOutcome.DENIED.value).is_equal_to("denied")
        assert_that(AuditOutcome.ERROR.value).is_equal_to("error")


class TestAuditEntry:
    def _entry(self) -> AuditEntry:
        return AuditEntry(
            id="06a09df1-2a3c-7482-8000-b6f138771978",
            timestamp=datetime(2026, 5, 17, 12, 0, tzinfo=UTC),
            outcome=AuditOutcome.DENIED,
            action="read",
            subject_type="Article",
            subject_id="article-1",
            actor_id="user-1",
            reason="article_unpublished",
            denial_surface="null",
            request_id="trace-abc",
            metadata=MappingProxyType({"adapter": "strawberry"}),
        )

    def test_required_fields_set(self) -> None:
        entry = self._entry()
        assert_that(entry.outcome).is_equal_to(AuditOutcome.DENIED)
        assert_that(entry.action).is_equal_to("read")
        assert_that(entry.subject_type).is_equal_to("Article")
        assert_that(entry.subject_id).is_equal_to("article-1")
        assert_that(entry.actor_id).is_equal_to("user-1")
        assert_that(entry.reason).is_equal_to("article_unpublished")
        assert_that(entry.denial_surface).is_equal_to("null")
        assert_that(entry.request_id).is_equal_to("trace-abc")
        assert_that(dict(entry.metadata)).is_equal_to({"adapter": "strawberry"})

    def test_entry_is_serializable_after_field_normalization(self) -> None:
        entry = self._entry()
        # Build a JSON-native payload manually -- ``dataclasses.asdict``
        # cannot deepcopy MappingProxyType, and the real audit stores
        # produce the dict shape below directly.
        payload = {
            "id": entry.id,
            "timestamp": entry.timestamp.isoformat(),
            "outcome": entry.outcome.value,
            "action": entry.action,
            "subject_type": entry.subject_type,
            "subject_id": entry.subject_id,
            "actor_id": entry.actor_id,
            "reason": entry.reason,
            "denial_surface": entry.denial_surface,
            "request_id": entry.request_id,
            "metadata": dict(entry.metadata),
        }
        rendered = json.dumps(payload)
        loaded = json.loads(rendered)
        assert_that(loaded["outcome"]).is_equal_to("denied")
        assert_that(loaded["subject_id"]).is_equal_to("article-1")

    def test_optional_fields_default_to_none_or_empty(self) -> None:
        e = AuditEntry(
            id="06a09df1-2a3c-7482-8000-b6f138771978",
            timestamp=datetime(2026, 5, 17, tzinfo=UTC),
            outcome=AuditOutcome.ALLOWED,
            action="read",
            subject_type="Article",
        )
        assert_that(e.subject_id).is_none()
        assert_that(e.actor_id).is_none()
        assert_that(e.reason).is_none()
        assert_that(e.denial_surface).is_none()
        assert_that(e.request_id).is_none()
        assert_that(dict(e.metadata)).is_empty()


class TestAuditStoreProtocol:
    def test_protocol_is_runtime_checkable_or_at_least_recognized(self) -> None:
        # The Protocol need not be runtime_checkable; we just verify a
        # structural-conforming class satisfies it under static typing.
        # narrow: use isinstance() only if @runtime_checkable, else structural OK
        class _Stub:
            async def write(self, entry: AuditEntry) -> None:  # noqa: D401
                """Minimal store stub."""
                return None

        store: AuditStore = _Stub()
        assert_that(callable(store.write)).is_true()
