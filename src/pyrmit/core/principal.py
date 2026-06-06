"""The Principal value type the engine passes to every policy."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Generic  # pep695-exempt: PEP 696 default needs Generic on 3.12

# PEP 696 TypeVar defaults require typing_extensions on Python 3.12 (the
# inline ``class Foo[E = str]:`` form lands in 3.13). When the project's
# minimum supported Python is 3.13+, switch to the inline form and drop
# the carve-out.
from typing_extensions import TypeVar  # pep695-exempt: see comment above

from pyrmit.core.entitlements import Entitlements

A = TypeVar("A")
E = TypeVar("E", default=str)


@dataclass(frozen=True)
class Principal(Generic[A, E]):  # pep695-exempt: see TypeVar carve-out above
    """An authenticated caller plus their entitlements.

    Bundles an application-defined ``actor`` value with an ``Entitlements``
    set and an optional request correlation identifier. Constructed once
    per request by the calling adapter and passed by value (frozen) to
    every policy invocation in that request.

    The second TypeVar ``E`` defaults to ``str``; explicit ``Principal[
    Actor, MyFeature]`` is required only when entitlements carry a
    non-string element type (e.g. an enum).

    Attributes:
        actor: User-defined value representing "who you are". Opaque to
            the engine; meaningful only inside policy functions.
        entitlements: An ``Entitlements[E]`` set representing "what you
            have" (tier-based features, paid capabilities, per-user
            grants). Use ``Entitlements.empty()`` when no entitlements
            apply to this request.
        request_id: Optional free-form correlation identifier (UUID, trace
            id, etc.) plumbed onto audit entries via ``AuditEntry.request_id``.
    """

    actor: A
    entitlements: Entitlements[E]
    request_id: str | None = None
