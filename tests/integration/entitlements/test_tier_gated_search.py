"""Tier-gated search acceptance scenarios.

Adding a new tier must be a configuration-only change -- no policy edits.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.principal import Principal
from pyrmit.entitlements.tier import TierEntitlementProvider


class Tier(StrEnum):
    FREE = "free"
    STANDARD = "standard"
    PRO = "pro"


class Feature(StrEnum):
    BASIC_SEARCH = "basic_search"
    ADVANCED_SEARCH = "advanced_search"
    UNLIMITED_BOOKMARKS = "unlimited_bookmarks"


class Action(StrEnum):
    SEARCH = "search"


@dataclass(frozen=True)
class Actor:
    user_id: str
    tier: Tier


@dataclass(frozen=True)
class SearchSubject:
    query: str
    required_feature: Feature


TIER_TABLE_V1: dict[Tier, frozenset[Feature]] = {
    Tier.FREE: frozenset({Feature.BASIC_SEARCH}),
    Tier.STANDARD: frozenset({Feature.BASIC_SEARCH, Feature.ADVANCED_SEARCH}),
    Tier.PRO: frozenset({
        Feature.BASIC_SEARCH,
        Feature.ADVANCED_SEARCH,
        Feature.UNLIMITED_BOOKMARKS,
    }),
}


def _engine() -> PolicyEngine[Principal[Actor, Feature], Action, SearchSubject]:
    engine: PolicyEngine[Principal[Actor, Feature], Action, SearchSubject] = PolicyEngine()

    @engine.policy(action=Action.SEARCH, subject_type=SearchSubject)
    def can_search(
        p: Principal[Actor, Feature],
        s: SearchSubject,
    ) -> Decision:
        if not p.entitlements.has(s.required_feature):
            return deny(
                "missing_required_entitlement",
                required=s.required_feature.value,
            )
        return ALLOW

    return engine


def _principal(
    actor: Actor,
    table: dict[Tier, frozenset[Feature]],
) -> Principal[Actor, Feature]:
    provider = TierEntitlementProvider[Actor, Feature, Tier](
        tier_for=lambda a: a.tier,
        table=table,
    )
    entitlements = asyncio.run(provider.entitlements_for(actor))
    return Principal(actor=actor, entitlements=entitlements)


class TestTierGatedSearch:
    def test_free_user_denied_advanced_search(self) -> None:
        engine = _engine()
        free_user = _principal(
            Actor(user_id="u1", tier=Tier.FREE),
            TIER_TABLE_V1,
        )
        subject = SearchSubject(
            query="anything",
            required_feature=Feature.ADVANCED_SEARCH,
        )
        d = engine.decide(
            principal=free_user,
            action=Action.SEARCH,
            subject=subject,
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("missing_required_entitlement")
        assert_that(d.detail["required"]).is_equal_to("advanced_search")

    def test_standard_user_allowed_advanced_search(self) -> None:
        engine = _engine()
        std = _principal(
            Actor(user_id="u2", tier=Tier.STANDARD),
            TIER_TABLE_V1,
        )
        d = engine.decide(
            principal=std,
            action=Action.SEARCH,
            subject=SearchSubject(
                query="x",
                required_feature=Feature.ADVANCED_SEARCH,
            ),
        )
        assert_that(d.allowed).is_true()

    def test_pro_user_allowed_unlimited_bookmarks(self) -> None:
        engine = _engine()
        pro = _principal(Actor(user_id="u3", tier=Tier.PRO), TIER_TABLE_V1)
        d = engine.decide(
            principal=pro,
            action=Action.SEARCH,
            subject=SearchSubject(
                query="x",
                required_feature=Feature.UNLIMITED_BOOKMARKS,
            ),
        )
        assert_that(d.allowed).is_true()

    def test_adding_a_new_tier_is_configuration_only(self) -> None:
        # Adding a tier and its feature set MUST be a configuration change
        # only -- the policy function MUST NOT need any edit.
        engine = _engine()  # same engine; same policy

        class TierV2(StrEnum):
            FREE = "free"
            STANDARD = "standard"
            PRO = "pro"
            ENTERPRISE = "enterprise"  # NEW

        table_v2: dict[TierV2, frozenset[Feature]] = {
            TierV2.FREE: TIER_TABLE_V1[Tier.FREE],
            TierV2.STANDARD: TIER_TABLE_V1[Tier.STANDARD],
            TierV2.PRO: TIER_TABLE_V1[Tier.PRO],
            TierV2.ENTERPRISE: frozenset({
                Feature.BASIC_SEARCH,
                Feature.ADVANCED_SEARCH,
                Feature.UNLIMITED_BOOKMARKS,
            }),
        }

        @dataclass(frozen=True)
        class ActorV2:
            user_id: str
            tier: TierV2

        provider = TierEntitlementProvider[ActorV2, Feature, TierV2](
            tier_for=lambda a: a.tier,
            table=table_v2,
        )
        ent = asyncio.run(provider.entitlements_for(ActorV2(user_id="exec", tier=TierV2.ENTERPRISE)))
        # Construct a principal with the V2 entitlements -- the existing
        # engine accepts it because the policy reads ``p.entitlements``
        # and is unaware of Tier types.
        principal: Principal[Actor, Feature] = Principal(
            actor=Actor(user_id="exec", tier=Tier.PRO),  # actor type unchanged
            entitlements=ent,
        )
        d = engine.decide(
            principal=principal,
            action=Action.SEARCH,
            subject=SearchSubject(
                query="x",
                required_feature=Feature.UNLIMITED_BOOKMARKS,
            ),
        )
        assert_that(d.allowed).is_true()
