"""Tests for TierEntitlementProvider."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.entitlements.tier import TierEntitlementProvider


class _Tier(StrEnum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"


class _Feature(StrEnum):
    BASIC = "basic"
    ADVANCED = "advanced"
    UNLIMITED = "unlimited"


@dataclass(frozen=True)
class _Actor:
    user_id: str
    tier: _Tier


TIER_TABLE: dict[_Tier, frozenset[_Feature]] = {
    _Tier.FREE: frozenset({_Feature.BASIC}),
    _Tier.STANDARD: frozenset({_Feature.BASIC, _Feature.ADVANCED}),
    _Tier.PRO: frozenset({_Feature.BASIC, _Feature.ADVANCED, _Feature.UNLIMITED}),
}


class TestTierEntitlementProvider:
    def test_two_step_lookup_maps_to_tier_features(self) -> None:
        provider = TierEntitlementProvider[_Actor, _Feature, _Tier](
            tier_for=lambda a: a.tier,
            table=TIER_TABLE,
        )
        alice = _Actor(user_id="alice", tier=_Tier.STANDARD)
        result = asyncio.run(provider.entitlements_for(alice))
        assert_that(set(result)).is_equal_to({_Feature.BASIC, _Feature.ADVANCED})

    def test_pro_tier_gets_all_features(self) -> None:
        provider = TierEntitlementProvider[_Actor, _Feature, _Tier](
            tier_for=lambda a: a.tier,
            table=TIER_TABLE,
        )
        result = asyncio.run(provider.entitlements_for(_Actor(user_id="root", tier=_Tier.PRO)))
        assert_that(set(result)).is_equal_to({_Feature.BASIC, _Feature.ADVANCED, _Feature.UNLIMITED})

    def test_unknown_tier_returns_empty(self) -> None:
        provider = TierEntitlementProvider[_Actor, _Feature, _Tier](
            tier_for=lambda a: a.tier,
            table={_Tier.FREE: frozenset({_Feature.BASIC})},
        )
        # PRO not in table.
        result = asyncio.run(provider.entitlements_for(_Actor(user_id="user", tier=_Tier.PRO)))
        assert_that(len(result)).is_equal_to(0)
