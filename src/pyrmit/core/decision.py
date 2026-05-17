"""Core decision types for the pyrmit policy engine.

Exports:
    Decision -- the immutable result of a single policy evaluation.
    ALLOW    -- the canonical allow decision.
    deny     -- helper for constructing a deny decision with a reason and
                optional immutable detail mapping.
    DenialSurface -- how a deny should surface through the calling adapter
                (FORBIDDEN, NULL, NOT_FOUND).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Final

# Permitted primitive value types for ``Decision.detail`` and
# ``AuditEntry.metadata``. JSON-serialisable, type-safe at the boundary,
# and broad enough for typical structured-context fields (counts, flags,
# stable identifiers) without expanding to arbitrary ``object``.
DetailValue = str | int | bool

_EMPTY_DETAIL: Final[Mapping[str, DetailValue]] = MappingProxyType({})


class DenialSurface(StrEnum):
    """How a deny is communicated outward by the calling adapter.

    Each policy registration binds one of these values; adapters interpret
    the surface per the framework's idioms (GraphQL: raise/null/typed error;
    REST: HTTP 403/404). See each adapter module's documentation for the
    per-framework mapping.
    """

    FORBIDDEN = "forbidden"
    NULL = "null"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class Decision:
    """The result of one policy evaluation.

    Attributes:
        allowed: True for allow, False for deny. No third state.
        reason: A short stable machine-readable identifier when ``allowed``
            is False (e.g. ``"article_unpublished"``). MUST be None when
            ``allowed`` is True.
        detail: Optional immutable mapping of structured context. Values
            MUST be ``str``, ``int``, or ``bool`` (JSON-primitive types
            that audit sinks can serialize natively). Defaults to an
            empty MappingProxyType.
    """

    allowed: bool
    reason: str | None = None
    detail: Mapping[str, DetailValue] = field(default=_EMPTY_DETAIL)

    def __post_init__(self) -> None:
        """Enforce allow/deny invariants, wrap ``detail``, validate primitives."""
        # Allowed decisions MUST NOT carry a reason; deny decisions MUST.
        # The docstring promises this; enforce it so callers cannot
        # smuggle a "soft deny" past audit by setting allowed=True with
        # a reason string, or a reasonless deny that has no machine-
        # readable identifier for the audit pipeline.
        if self.allowed and self.reason is not None:
            msg = (
                f"Decision(allowed=True) must have reason=None; "
                f"got reason={self.reason!r}. Use Decision(allowed=True) "
                f"or the ALLOW singleton for allows."
            )
            raise ValueError(msg)
        if not self.allowed and self.reason is None:
            msg = "Decision(allowed=False) must have a non-None reason; use deny('some_machine_readable_reason')."
            raise ValueError(msg)
        # Runtime guard: a downstream caller could pass a mutable dict or
        # a typed-but-wrong value via an ``Any``-typed boundary. Validate.
        for key, value in self.detail.items():
            # ``bool`` is a subclass of ``int`` so the order matters: we
            # accept ``bool`` and ``int`` distinctly to make the contract
            # explicit in error messages.
            if not isinstance(value, str | int):
                msg = (
                    f"Decision.detail values must be str | int | bool; "
                    f"key={key!r} has value of type {type(value).__name__}"
                )
                raise TypeError(msg)
        if not isinstance(self.detail, MappingProxyType):
            object.__setattr__(self, "detail", MappingProxyType(dict(self.detail)))


ALLOW: Final[Decision] = Decision(allowed=True)


def deny(reason: str, /, **detail: DetailValue) -> Decision:
    """Construct a deny Decision with a stable reason and optional detail.

    Args:
        reason: Machine-readable reason; positional-only so calls read
            naturally as ``deny("article_unpublished")``.
        **detail: Optional structured context; values MUST be
            ``str``, ``int``, or ``bool`` (JSON-primitive).

    Returns:
        A new frozen Decision with ``allowed=False`` and an immutable
        ``detail`` mapping.
    """
    if detail:
        frozen_detail: Mapping[str, DetailValue] = MappingProxyType(dict(detail))
        return Decision(allowed=False, reason=reason, detail=frozen_detail)
    return Decision(allowed=False, reason=reason, detail=_EMPTY_DETAIL)
