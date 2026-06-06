"""AuditEntry.metadata is defensively copied so persisted records cannot drift."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from types import MappingProxyType
from typing import cast

import pytest
from assertpy import assert_that

from pyrmit.core.audit import AuditEntry, AuditOutcome
from pyrmit.core.decision import DetailValue


def _entry(*, metadata: Mapping[str, DetailValue]) -> AuditEntry:
    return AuditEntry(
        id="06a09df1-2a3c-7482-8000-b6f138771978",
        timestamp=datetime(2026, 1, 1, tzinfo=UTC),
        outcome=AuditOutcome.ALLOWED,
        action="read",
        subject_type="Article",
        metadata=metadata,
    )


class TestAuditEntryMetadataImmutability:
    def test_direct_constructor_defensively_copies_mutable_dict(self) -> None:
        original: dict[str, DetailValue] = {"k": "v"}
        entry = _entry(metadata=original)
        original["k"] = "mutated"
        original["new"] = "added"
        assert_that(dict(entry.metadata)).is_equal_to({"k": "v"})

    def test_metadata_is_a_mappingproxytype_after_construction(self) -> None:
        entry = _entry(metadata={"k": "v"})
        assert_that(isinstance(entry.metadata, MappingProxyType)).is_true()

    def test_existing_mappingproxytype_is_not_rewrapped(self) -> None:
        proxy: MappingProxyType[str, DetailValue] = MappingProxyType({"k": "v"})
        entry = _entry(metadata=proxy)
        assert_that(entry.metadata).is_same_as(proxy)

    def test_int_and_bool_values_accepted(self) -> None:
        entry = _entry(metadata={"count": 5, "ok": True, "name": "alice"})
        assert_that(dict(entry.metadata)).is_equal_to({"count": 5, "ok": True, "name": "alice"})

    def test_non_primitive_value_rejected_at_construction(self) -> None:
        with pytest.raises(TypeError) as exc_info:
            _entry(metadata=cast(dict[str, DetailValue], {"bad": {"nested": True}}))
        assert_that(str(exc_info.value)).contains("str | int | bool")
