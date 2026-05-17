"""InMemoryAuditStore -- bounded ring buffer; default for tests."""

from __future__ import annotations

import asyncio
from collections import deque

from pyrmit.core.audit import AuditEntry


class InMemoryAuditStore:
    """Bounded in-memory audit store.

    Backed by ``collections.deque(maxlen=capacity)`` so the oldest
    entries are evicted when the buffer overflows. Reads are snapshot
    tuples -- safe to iterate while a producer is writing.

    Async/sync surface:
        ``write`` is async (it satisfies the ``AuditStore`` protocol
        and takes the internal ``asyncio.Lock``); ``entries()`` and
        ``clear()`` are intentionally **sync** -- they are inspection
        / test-setup helpers and never block the event loop. This
        asymmetry is by design: tests can call ``entries()`` from
        regular pytest functions without dragging async-fixture
        machinery into the assertion path.
    """

    __slots__ = ("_entries", "_lock")

    def __init__(self, *, capacity: int = 1024) -> None:
        """Construct a bounded in-memory store.

        Args:
            capacity: Maximum number of entries retained. Older entries
                are evicted when the buffer is full.
        """
        self._entries: deque[AuditEntry] = deque(maxlen=capacity)
        self._lock: asyncio.Lock = asyncio.Lock()

    async def write(self, entry: AuditEntry) -> None:
        """Append ``entry`` to the buffer; evict the oldest if needed."""
        async with self._lock:
            self._entries.append(entry)

    def entries(self) -> tuple[AuditEntry, ...]:
        """Return a snapshot tuple of the buffer's current contents."""
        return tuple(self._entries)

    def clear(self) -> None:
        """Clear all retained entries."""
        self._entries.clear()
