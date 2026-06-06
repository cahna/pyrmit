"""StubEntitlementProvider -- testing helper that raises on unknown lookups."""

from __future__ import annotations

from collections.abc import Mapping

from pyrmit.core.entitlements import Entitlements


class StubEntitlementProvider[LookupT, FeatureT]:
    """Like ``StaticEntitlementProvider`` but raises on unknown lookups.

    Used in tests that want to ASSERT no surprise lookups occurred. The
    static provider silently maps unknown lookups to empty -- this stub
    fails loudly instead, so a test that exercises an unexpected lookup
    surfaces immediately rather than producing a misleading deny.
    """

    __slots__ = ("_mapping",)

    def __init__(self, *, mapping: Mapping[LookupT, frozenset[FeatureT]]) -> None:
        """Construct from a lookup -> frozenset mapping.

        Args:
            mapping: A mapping from ``LookupT`` to the ``frozenset`` of
                features that lookup holds. Missing keys raise ``KeyError``.
        """
        self._mapping: Mapping[LookupT, frozenset[FeatureT]] = mapping

    async def entitlements_for(
        self,
        lookup: LookupT,
    ) -> Entitlements[FeatureT]:
        """Look up ``lookup`` or raise ``KeyError`` if unknown."""
        if lookup not in self._mapping:
            msg = f"StubEntitlementProvider: unknown lookup {lookup!r}"
            raise KeyError(msg)
        return Entitlements[FeatureT](self._mapping[lookup])
