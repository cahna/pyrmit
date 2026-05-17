"""StaticEntitlementProvider -- fixed mapping for tests and demos."""

from __future__ import annotations

from collections.abc import Mapping

from pyrmit.core.entitlements import Entitlements


class StaticEntitlementProvider[LookupT, FeatureT]:
    """Return entitlements from a fixed mapping; unknown lookups -> empty."""

    __slots__ = ("_mapping",)

    def __init__(self, *, mapping: Mapping[LookupT, frozenset[FeatureT]]) -> None:
        """Construct from a lookup -> frozenset mapping.

        Args:
            mapping: A mapping from ``LookupT`` to the ``frozenset`` of
                features that lookup holds. Missing keys yield
                ``Entitlements.empty()``.
        """
        self._mapping: Mapping[LookupT, frozenset[FeatureT]] = mapping

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Look up ``lookup`` in the static mapping."""
        items = self._mapping.get(lookup)
        if items is None:
            return Entitlements[FeatureT].empty()
        return Entitlements[FeatureT](items)
