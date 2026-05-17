"""LoggingAuditStore -- writes audit entries to stdlib logging at INFO."""

from __future__ import annotations

import logging

from pyrmit.core.audit import AuditEntry


class LoggingAuditStore:
    """Audit store that logs each entry at INFO via stdlib ``logging``.

    Uses deferred ``%``-style formatting via the ``logger`` API so that
    structured-log adapters and sampling work correctly. Adds no handler,
    sets no level, and never calls ``basicConfig`` -- the host application
    owns the logging stack.

    .. warning::

        The ``actor_id`` and ``subject_id`` fields written here are
        resolved via your engine's configured resolvers and are
        frequently considered **PII** under GDPR / CCPA / similar
        regimes, even when they're surrogate identifiers (UUIDs, hashed
        emails). Choose downstream log sinks accordingly: ship audit
        logs to systems with appropriate retention, access controls,
        and right-to-erasure tooling. If you cannot meet those
        requirements, use :class:`pyrmit.audit.memory.InMemoryAuditStore`
        for tests and roll your own redacting sink for production.
    """

    __slots__ = ("_logger",)

    def __init__(self, *, logger_name: str = "pyrmit.audit") -> None:
        """Construct the store.

        Args:
            logger_name: The stdlib logger name to write to. Defaults to
                ``"pyrmit.audit"``.
        """
        self._logger: logging.Logger = logging.getLogger(logger_name)

    async def write(self, entry: AuditEntry) -> None:
        """Log ``entry`` at INFO with structured key=value fields."""
        # Deferred format string -- the logger decides whether to render
        # based on its configured level.
        self._logger.info(
            "authz outcome=%s action=%s subject_type=%s "
            "subject_id=%s actor_id=%s reason=%s denial_surface=%s "
            "request_id=%s id=%s",
            entry.outcome.value,
            entry.action,
            entry.subject_type,
            entry.subject_id,
            entry.actor_id,
            entry.reason,
            entry.denial_surface,
            entry.request_id,
            entry.id,
        )
