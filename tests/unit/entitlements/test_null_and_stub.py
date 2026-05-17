"""Tests for NullEntitlementProvider and StubEntitlementProvider."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from assertpy import assert_that

from pyrmit.entitlements.null import NullEntitlementProvider
from pyrmit.entitlements.stub import StubEntitlementProvider


class _Feature(StrEnum):
    A = "a"


class TestNullEntitlementProvider:
    def test_always_empty(self) -> None:
        provider = NullEntitlementProvider[str, _Feature]()
        result = asyncio.run(provider.entitlements_for("anyone"))
        assert_that(len(result)).is_equal_to(0)

    def test_different_lookups_both_empty(self) -> None:
        provider = NullEntitlementProvider[str, _Feature]()
        for k in ("a", "b", "c"):
            r = asyncio.run(provider.entitlements_for(k))
            assert_that(len(r)).described_as(k).is_equal_to(0)


class TestStubEntitlementProvider:
    def test_known_lookup_returns_mapped(self) -> None:
        provider = StubEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.A})})
        result = asyncio.run(provider.entitlements_for("alice"))
        assert_that(set(result)).is_equal_to({_Feature.A})

    def test_unknown_lookup_raises_key_error(self) -> None:
        provider = StubEntitlementProvider[str, _Feature](mapping={})
        try:
            asyncio.run(provider.entitlements_for("ghost"))
        except KeyError:
            return
        assert_that(False).described_as("expected KeyError").is_true()
