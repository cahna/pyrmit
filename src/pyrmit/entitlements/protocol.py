"""The EntitlementProvider Protocol -- user-implemented entitlement source."""

from __future__ import annotations

from typing import Protocol

from pyrmit.core.entitlements import Entitlements


class EntitlementProvider[LookupT, FeatureT](Protocol):
    """User-implements: 'what entitlements does this lookup hold?'.

    The library invokes this exactly once per request from the adapter,
    then sets the result on the request principal for the request
    lifetime. The Protocol is generic over an application-defined
    ``LookupT`` (typically an actor, an account id, a tenant struct, or
    a composite) and an application-defined ``FeatureT`` (typically a
    ``StrEnum``).

    Returning ``Entitlements.empty()`` is the fail-closed default;
    callers MAY return an empty set when they cannot service a lookup
    rather than raising. The CompositeEntitlementProvider catches
    exceptions from inner providers and substitutes an empty set, but
    direct usage should prefer an empty return.
    """

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Return the entitlements associated with ``lookup``."""
        ...
