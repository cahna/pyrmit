"""NullEntitlementProvider -- always returns the empty set."""

from __future__ import annotations

from pyrmit.core.entitlements import Entitlements


class NullEntitlementProvider[LookupT, FeatureT]:
    """Provider that always returns ``Entitlements.empty()``.

    Use to make "no entitlements" explicit in demos and tests, rather
    than passing ``None`` as the entitlement provider somewhere.
    """

    __slots__ = ()

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Ignore ``lookup`` and return the empty entitlement set."""
        del lookup
        return Entitlements[FeatureT].empty()
