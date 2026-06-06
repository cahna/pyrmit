"""Concurrent cold-cache misses on the same key must dedupe to one inner call.

Regression test for the thundering-herd risk in
:class:`pyrmit.entitlements.cached.CachedEntitlementProvider`. Before the
in-flight Future dedup was added, N concurrent ``entitlements_for(same_key)``
calls on a cold cache would all invoke the inner provider in parallel.
"""

from __future__ import annotations

import asyncio
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.cached import CachedEntitlementProvider


class _Feature(StrEnum):
    A = "a"


class _SlowCountingProvider:
    """Counts inner calls and yields control before returning.

    The ``asyncio.sleep(0)`` is critical: it ensures the leader yields
    to the event loop after registering its in-flight Future, giving
    followers a chance to observe it before the leader resolves.
    """

    def __init__(self) -> None:
        self.calls: dict[str, int] = {}

    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """Increment the counter, yield once, then return a fixed result."""
        self.calls[lookup] = self.calls.get(lookup, 0) + 1
        await asyncio.sleep(0)
        return Entitlements[_Feature](frozenset({_Feature.A}))


class _FlakyProvider:
    """Raises on first call; succeeds on subsequent calls."""

    def __init__(self) -> None:
        self.calls: int = 0

    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """First call raises; later calls return an empty set."""
        del lookup
        self.calls += 1
        if self.calls == 1:
            raise RuntimeError("transient")
        return Entitlements[_Feature](frozenset())


class TestConcurrentCacheMisses:
    def test_concurrent_cold_cache_misses_call_inner_once(self) -> None:
        inner = _SlowCountingProvider()
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=60,
            max_entries=128,
        )

        async def _gather() -> list[Entitlements[_Feature]]:
            return await asyncio.gather(*[cached.entitlements_for("alice") for _ in range(16)])

        results = asyncio.run(_gather())
        assert_that(results).is_length(16)
        # Critical property: inner was called exactly once despite 16 concurrent callers.
        assert_that(inner.calls.get("alice", 0)).is_equal_to(1)
        # All callers got the same result value.
        for r in results:
            assert_that(list(r)).is_equal_to([_Feature.A])

    def test_failure_does_not_persist_after_inflight_cleanup(self) -> None:
        """A leader failure must not leave a poisoned in-flight Future behind."""
        inner = _FlakyProvider()
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=60,
            max_entries=128,
        )

        raised = False
        try:
            asyncio.run(cached.entitlements_for("alice"))
        except RuntimeError:
            raised = True
        assert_that(raised).is_true()

        # The next call must enter the leader path again -- proves
        # _inflight was cleaned up by the previous failure.
        result = asyncio.run(cached.entitlements_for("alice"))
        assert_that(inner.calls).is_equal_to(2)
        assert_that(list(result)).is_equal_to([])

    def test_leader_cancellation_does_not_poison_inflight_or_followers(self) -> None:
        """Cancelling the leader leaves _inflight clean for the next caller.

        Before the cancellation fix, ``except BaseException`` swallowed
        ``CancelledError`` and set it as the Future's exception, which
        would pollute any follower awaiting that Future and corrupt
        cancellation semantics. The current behavior cancels the Future
        explicitly so followers see a CancelledError that's structurally
        their own concern, and clears ``_inflight`` so the next caller
        becomes a fresh leader.
        """

        class _ToggleProvider:
            """First call awaits forever; subsequent calls return promptly."""

            def __init__(self) -> None:
                self.calls: int = 0

            async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
                del lookup
                self.calls += 1
                if self.calls == 1:
                    await asyncio.sleep(3600)
                return Entitlements[_Feature](frozenset({_Feature.A}))

        inner = _ToggleProvider()
        cached = CachedEntitlementProvider[str, _Feature](
            inner=inner,
            ttl_seconds=60,
            max_entries=128,
        )

        async def _run() -> Entitlements[_Feature]:
            leader = asyncio.create_task(cached.entitlements_for("alice"))
            # Allow the leader to register the in-flight Future.
            await asyncio.sleep(0)
            leader.cancel()
            try:
                await leader
            except asyncio.CancelledError:
                pass
            # The next call must enter the leader path again -- proves
            # _inflight was cleaned up by the cancellation.
            return await cached.entitlements_for("alice")

        result = asyncio.run(_run())
        assert_that(list(result)).is_equal_to([_Feature.A])
        # Two leader invocations: the cancelled one and the second caller.
        assert_that(inner.calls).is_equal_to(2)
