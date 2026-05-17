"""TierEntitlementProvider -- two-step tier -> feature-set lookup."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from pyrmit.core.entitlements import Entitlements


class TierEntitlementProvider[LookupT, FeatureT, TierT]:
    """Resolve a tier from a lookup, then map the tier to a feature set.

    Adding a new tier is a configuration change (extend ``table``); no
    policy edits are required. The ``tier_for`` callable extracts the
    tier from the lookup (often ``lambda actor: actor.tier``).
    """

    __slots__ = ("_table", "_tier_for")

    def __init__(
        self,
        *,
        tier_for: Callable[[LookupT], TierT],
        table: Mapping[TierT, frozenset[FeatureT]],
    ) -> None:
        """Construct from a tier-extractor callable and a tier-to-features table.

        Args:
            tier_for: Callable extracting the ``TierT`` value from a lookup.
            table: Mapping from each tier to the frozenset of features that
                tier carries. A tier missing from ``table`` yields an empty
                entitlement set.
        """
        self._tier_for: Callable[[LookupT], TierT] = tier_for
        self._table: Mapping[TierT, frozenset[FeatureT]] = table

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Extract the tier and look it up in the feature table."""
        tier = self._tier_for(lookup)
        items = self._table.get(tier)
        if items is None:
            return Entitlements[FeatureT].empty()
        return Entitlements[FeatureT](items)
