"""Audit entry types and the pluggable AuditStore protocol.

The engine emits an ``AuditEntry`` from ``adecide`` to a user-supplied
``AuditStore`` per the configured outcome filter. Reference stores live
under ``pyrmit.audit``; users may implement their own by satisfying the
``AuditStore`` Protocol structurally.

``AuditStore.write`` is a plug-in I/O boundary: implementations MAY raise
``Exception`` on write failure, and the engine catches at that boundary
and applies the configured ``PolicyEngine.audit_failure_mode``.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Final, Protocol

from pyrmit.core.decision import DetailValue

_EMPTY_METADATA: Final[Mapping[str, DetailValue]] = MappingProxyType({})


class AuditOutcome(StrEnum):
    """The decision outcome category recorded in audit."""

    ALLOWED = "allowed"
    DENIED = "denied"
    ERROR = "error"


@dataclass(frozen=True)
class AuditEntry:
    """A structured record of one authorization decision.

    Attributes:
        id: Sortable identifier (UUIDv7 hex string).
        timestamp: tz-aware UTC datetime of the decision.
        outcome: The ``AuditOutcome`` category.
        action: ``str(action_value)`` for the action enum.
        subject_type: ``type(subject).__name__``.
        subject_id: Resolved via a registered subject-id resolver; None if
            no resolver is registered. NEVER ``repr(subject)``.
        actor_id: Resolved via the engine's ``actor_id`` callable; None if
            none is configured. NEVER ``repr(actor)``. WARNING: applications
            should treat resolved ``actor_id`` / ``subject_id`` values as
            PII under most data-protection regimes (GDPR, CCPA) and select
            audit sinks accordingly.
        reason: ``Decision.reason``.
        denial_surface: The binding's ``DenialSurface.value``; None for
            allowed entries.
        request_id: ``Principal.request_id``.
        metadata: Adapter-supplied immutable mapping; values MUST be
            ``str``, ``int``, or ``bool``. Defaults to an empty
            MappingProxyType.
    """

    id: str
    timestamp: datetime
    outcome: AuditOutcome
    action: str
    subject_type: str
    subject_id: str | None = None
    actor_id: str | None = None
    reason: str | None = None
    denial_surface: str | None = None
    request_id: str | None = None
    metadata: Mapping[str, DetailValue] = field(default=_EMPTY_METADATA)

    def __post_init__(self) -> None:
        """Defensively wrap ``metadata`` and validate value primitives."""
        # Mirror the Decision.detail guard: a caller routing through an
        # ``Any``-typed adapter boundary can violate the typed contract.
        # Reject at construction so audit records stay JSON-serialisable.
        for key, value in self.metadata.items():
            if not isinstance(value, str | int):
                msg = (
                    f"AuditEntry.metadata values must be str | int | bool; "
                    f"key={key!r} has value of type {type(value).__name__}"
                )
                raise TypeError(msg)
        if not isinstance(self.metadata, MappingProxyType):
            object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))


class AuditStore(Protocol):
    """Pluggable destination for AuditEntry records.

    Implementations MAY raise ``Exception`` (not ``BaseException``) on
    write failure; the engine catches at the boundary and applies the
    configured ``audit_failure_mode``.
    """

    async def write(self, entry: AuditEntry) -> None:
        """Persist one audit entry."""
        ...
