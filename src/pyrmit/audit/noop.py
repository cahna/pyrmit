"""NoopAuditStore -- explicit no-op for audit-disabled deployments."""

from __future__ import annotations

from pyrmit.core.audit import AuditEntry


class NoopAuditStore:
    """Audit store that drops every entry.

    Preferred over passing ``audit=None`` when you want the engine's
    audit-dispatch code path exercised consistently while silencing
    every entry. Useful for benchmarks and production environments
    where audit is explicitly disabled.
    """

    __slots__ = ()

    async def write(self, entry: AuditEntry) -> None:
        """Drop ``entry`` on the floor."""
        del entry
