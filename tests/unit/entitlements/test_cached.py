"""Tests for CachedEntitlementProvider."""

from __future__ import annotations

import asyncio
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.cached import CachedEntitlementProvider


class _Feature(StrEnum):
    A = "a"
    B = "b"


class _CountingProvider:
    """Counts how many times entitlements_for is called per lookup."""

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}
        self.next_result: dict[str, frozenset[_Feature]] = {}

    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """Track invocation count and return the latest stored result."""
        self.calls[lookup] = self.calls.get(lookup, 0) + 1
        return Entitlements[_Feature](self.next_result.get(lookup, frozenset()))


class _RaisingProvider:
    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """Always raise; used to verify failures are NOT cached."""
        del lookup
        raise RuntimeError("transient failure")


class TestCachedEntitlementProvider:
    def test_inner_called_once_within_ttl(self) -> None:
        inner = _CountingProvider()
        inner.next_result["alice"] = frozenset({_Feature.A})
        now = [100.0]
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=60,
            max_entries=128,
            clock=lambda: now[0],
        )

        asyncio.run(cached.entitlements_for("alice"))
        asyncio.run(cached.entitlements_for("alice"))
        asyncio.run(cached.entitlements_for("alice"))

        assert_that(inner.calls.get("alice", 0)).is_equal_to(1)

    def test_inner_called_again_after_ttl_expires(self) -> None:
        inner = _CountingProvider()
        inner.next_result["alice"] = frozenset({_Feature.A})
        now = [100.0]
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=10,
            max_entries=128,
            clock=lambda: now[0],
        )

        asyncio.run(cached.entitlements_for("alice"))
        now[0] = 200.0  # past TTL
        asyncio.run(cached.entitlements_for("alice"))

        assert_that(inner.calls.get("alice", 0)).is_equal_to(2)

    def test_lru_eviction_at_max_entries(self) -> None:
        inner = _CountingProvider()
        for k in ("a", "b", "c", "d"):
            inner.next_result[k] = frozenset({_Feature.A})
        now = [0.0]
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=999,
            max_entries=2,
            clock=lambda: now[0],
        )

        asyncio.run(cached.entitlements_for("a"))
        asyncio.run(cached.entitlements_for("b"))
        # cache: {a, b}; max=2. Adding c evicts a.
        asyncio.run(cached.entitlements_for("c"))
        # a was evicted; re-lookup recalls inner.
        asyncio.run(cached.entitlements_for("a"))

        assert_that(inner.calls.get("a", 0)).is_equal_to(2)
        assert_that(inner.calls.get("b", 0)).is_equal_to(1)
        assert_that(inner.calls.get("c", 0)).is_equal_to(1)

    def test_failures_are_not_cached(self) -> None:
        bad = _RaisingProvider()
        cached = CachedEntitlementProvider[str, _Feature](
            inner=bad,
            ttl_seconds=60,
            max_entries=128,
        )
        # Each call should propagate the raise.
        raised_first = False
        raised_second = False
        try:
            asyncio.run(cached.entitlements_for("x"))
        except RuntimeError:
            raised_first = True
        try:
            asyncio.run(cached.entitlements_for("x"))
        except RuntimeError:
            raised_second = True
        assert_that(raised_first).is_true()
        assert_that(raised_second).is_true()
