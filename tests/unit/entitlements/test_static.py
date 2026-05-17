"""Tests for StaticEntitlementProvider."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.static import StaticEntitlementProvider


class _Feature(StrEnum):
    BASIC = "basic"
    PRO = "pro"


class TestStaticEntitlementProvider:
    def test_known_lookup_returns_mapped_set(self) -> None:
        mapping: dict[str, frozenset[_Feature]] = {
            "alice": frozenset({_Feature.BASIC, _Feature.PRO}),
            "bob": frozenset({_Feature.BASIC}),
        }
        provider = StaticEntitlementProvider[str, _Feature](mapping=mapping)
        result = asyncio.run(provider.entitlements_for("alice"))
        assert_that(set(result)).is_equal_to({_Feature.BASIC, _Feature.PRO})

    def test_unknown_lookup_returns_empty(self) -> None:
        provider = StaticEntitlementProvider[str, _Feature](mapping={})
        result = asyncio.run(provider.entitlements_for("ghost"))
        assert_that(len(result)).is_equal_to(0)
        assert_that(result).is_equal_to(Entitlements[_Feature].empty())

    def test_repeated_lookups_are_idempotent(self) -> None:
        mapping: dict[str, frozenset[_Feature]] = {
            "alice": frozenset({_Feature.BASIC}),
        }
        provider = StaticEntitlementProvider[str, _Feature](mapping=mapping)
        first = asyncio.run(provider.entitlements_for("alice"))
        second = asyncio.run(provider.entitlements_for("alice"))
        assert_that(first).is_equal_to(second)
