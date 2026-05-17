"""CachedEntitlementProvider -- TTL + LRU cache wrapping an inner provider."""

from __future__ import annotations

import asyncio
import time
from collections import OrderedDict
from collections.abc import Callable

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.protocol import EntitlementProvider


class CachedEntitlementProvider[LookupT, FeatureT]:
    """TTL- and LRU-bounded cache around an inner entitlement provider.

    Failures from the inner provider are NOT cached -- they propagate.
    This prevents a transient outage from being amplified into TTL-long
    deny periods.

    Concurrent cold-cache misses on the same key are deduplicated via an
    in-flight ``asyncio.Future`` map: the first caller becomes the
    "leader" that invokes the inner provider; followers await the leader's
    Future and receive the same result without re-invoking the inner
    provider. Cache hits stay lock-free.

    Cache eviction policy:
        - Entries past ``ttl_seconds`` are recomputed.
        - When ``max_entries`` is reached, the least-recently-used entry
          is evicted to make room.
    """

    __slots__ = ("_cache", "_clock", "_inflight", "_inner", "_max_entries", "_ttl_seconds")

    def __init__(
        self,
        *,
        inner: EntitlementProvider[LookupT, FeatureT],
        ttl_seconds: int = 60,
        max_entries: int = 1024,
        clock: Callable[[], float] | None = None,
    ) -> None:
        """Construct around an inner provider.

        Args:
            inner: The wrapped provider whose results are cached.
            ttl_seconds: Time-to-live for each cache entry, in seconds.
            max_entries: Maximum number of cache entries before LRU eviction.
            clock: Optional monotonic clock source for testing; defaults to
                ``time.monotonic`` in production.
        """
        self._inner: EntitlementProvider[LookupT, FeatureT] = inner
        self._ttl_seconds: int = ttl_seconds
        self._max_entries: int = max_entries
        self._clock: Callable[[], float] = clock or time.monotonic
        # Maps lookup -> (timestamp, entitlements). OrderedDict gives us
        # both LRU semantics (move_to_end on read) and O(1) eviction.
        self._cache: OrderedDict[LookupT, tuple[float, Entitlements[FeatureT]]] = OrderedDict()
        # Maps lookup -> in-flight Future. Populated by the leader at the
        # start of a cold-cache call and removed when the call completes
        # (success or failure). Followers await the leader's Future
        # instead of invoking the inner provider in parallel.
        self._inflight: dict[LookupT, asyncio.Future[Entitlements[FeatureT]]] = {}

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Return cached result if fresh; otherwise defer to ``inner`` and cache.

        Concurrent callers on the same key are deduplicated: at most one
        ``inner.entitlements_for`` call is in flight per key at any time.
        """
        now = self._clock()
        cached = self._cache.get(lookup)
        if cached is not None:
            timestamp, items = cached
            if now - timestamp < self._ttl_seconds:
                self._cache.move_to_end(lookup)
                return items
            del self._cache[lookup]

        # If another coroutine is already loading this key, await its
        # result instead of starting a parallel inner call.
        inflight = self._inflight.get(lookup)
        if inflight is not None:
            return await inflight

        # We are the leader for this key.
        future: asyncio.Future[Entitlements[FeatureT]] = asyncio.get_running_loop().create_future()
        self._inflight[lookup] = future
        try:
            result = await self._inner.entitlements_for(lookup)
        except asyncio.CancelledError:
            # Cancellation is local to the cancelled task. Followers
            # awaiting this Future must NOT be cancelled-by-leader -- their
            # own coroutines were not cancelled. Drop the in-flight entry
            # so the next caller becomes a fresh leader, leave the Future
            # un-resolved (any current followers will see CancelledError
            # naturally via the Future's own cancellation), and re-raise
            # in the leader only.
            self._inflight.pop(lookup, None)
            if not future.done():
                future.cancel()
            raise
        except Exception as exc:
            # Failures are not cached -- propagate to the leader and to
            # any followers awaiting our Future.
            if not future.done():
                future.set_exception(exc)
            self._inflight.pop(lookup, None)
            # Mark the exception as retrieved so asyncio doesn't warn at
            # GC time when no follower happened to await this Future.
            future.exception()
            raise

        self._cache[lookup] = (now, result)
        while len(self._cache) > self._max_entries:
            # Pop oldest (LRU).
            self._cache.popitem(last=False)
        if not future.done():
            future.set_result(result)
        self._inflight.pop(lookup, None)
        return result
