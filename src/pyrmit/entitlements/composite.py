"""CompositeEntitlementProvider -- union of inner provider results."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Sequence
from typing import Final

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.protocol import EntitlementProvider

_LOGGER: Final[logging.Logger] = logging.getLogger("pyrmit.entitlements.composite")


class CompositeEntitlementProvider[LookupT, FeatureT]:
    """Union of one or more inner entitlement providers.

    Inner providers are queried concurrently via ``asyncio.gather``.
    Failures in any inner provider are caught at the boundary: the
    failing provider contributes an empty set, a WARNING is emitted on
    ``pyrmit.entitlements.composite``, and the union of the remaining
    successful providers is returned. This is the fail-closed posture --
    a failed provider yields no entitlements, which is more restrictive
    than provisioning one it shouldn't.
    """

    __slots__ = ("_providers",)

    def __init__(
        self,
        *,
        providers: Sequence[EntitlementProvider[LookupT, FeatureT]],
    ) -> None:
        """Construct from a sequence of inner providers.

        Args:
            providers: The inner ``EntitlementProvider`` implementations
                to union. An empty sequence yields an empty entitlement set
                for every lookup.
        """
        self._providers: Sequence[EntitlementProvider[LookupT, FeatureT]] = providers

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Concurrently query every inner provider and union their results."""
        if not self._providers:
            return Entitlements[FeatureT].empty()

        results = await asyncio.gather(
            *(p.entitlements_for(lookup) for p in self._providers),
            return_exceptions=True,
        )
        union_items: set[FeatureT] = set()
        for index, result in enumerate(results):
            # Cancellation MUST propagate -- treating ``CancelledError``
            # like an ordinary provider failure (empty entitlements) would
            # silently corrupt cancellation semantics for the caller. The
            # task cancelled by the runtime is the one we belong to.
            if isinstance(result, asyncio.CancelledError):
                raise result
            if isinstance(result, BaseException):
                # Log only the exception type and provider index; do NOT
                # interpolate ``str(result)`` because inner-provider
                # messages frequently carry user-supplied identifiers
                # (e.g. "user X not found") that downstream log sinks
                # may consider PII under GDPR/CCPA.
                _LOGGER.warning(
                    "entitlement provider %d failed for lookup; treating as empty set (%s)",
                    index,
                    type(result).__name__,
                )
                continue
            for item in result:
                union_items.add(item)
        return Entitlements[FeatureT](frozenset(union_items))
