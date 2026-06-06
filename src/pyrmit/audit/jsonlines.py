"""JsonLinesAuditStore -- append-only JSON Lines file sink."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from pyrmit.core.audit import AuditEntry


class JsonLinesAuditStore:
    """Append-only JSON Lines audit store.

    One JSON object per line, UTF-8 encoded. Each call to ``write``
    opens the destination file in append mode, writes the line, and
    closes the file -- so durability is immediate (no in-process buffer
    to flush). File I/O runs through ``asyncio.to_thread`` so the event
    loop is never blocked. ``aclose()`` is a documented no-op kept for
    API parity with buffered stores.
    """

    __slots__ = ("_encoding", "_lock", "_path")

    def __init__(
        self,
        *,
        path: Path,
        encoding: str = "utf-8",
    ) -> None:
        """Construct the store.

        Args:
            path: Destination file path. Created on first write.
            encoding: File encoding. Default UTF-8.
        """
        self._path: Path = path
        self._encoding: str = encoding
        self._lock: asyncio.Lock = asyncio.Lock()

    @staticmethod
    def _serialize(entry: AuditEntry) -> str:
        """Render one AuditEntry to a single JSON line (no trailing newline)."""
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
        return json.dumps(payload, ensure_ascii=False)

    def _append_sync(self, line: str) -> None:
        """Append one line + newline; create the file on first write."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        with self._path.open("a", encoding=self._encoding) as fh:
            fh.write(line)
            fh.write("\n")

    async def write(self, entry: AuditEntry) -> None:
        """Serialize ``entry`` and append to the file."""
        line = self._serialize(entry)
        async with self._lock:
            await asyncio.to_thread(self._append_sync, line)

    async def aclose(self) -> None:
        """No-op kept for API parity with buffered implementations.

        Files are opened and closed per write, so there is no persistent
        handle to flush. Calling ``aclose()`` is always safe and never
        raises.
        """
        return None
