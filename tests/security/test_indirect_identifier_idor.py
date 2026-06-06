"""Indirect-identifier IDOR security test.

A mutation accepts a ``code_id`` and ALSO an unrelated ``match_id`` arg.
The subject loader walks ``code -> match`` from authoritative sources;
attacker-supplied ``match_id`` values MUST have ZERO influence on the
decision.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

import strawberry
from assertpy import assert_that
from strawberry.types import Info

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    REGISTER = "register"


@dataclass(frozen=True)
class Actor:
    user_id: UUID


@dataclass(frozen=True)
class Match:
    id: UUID
    owner_id: UUID


@dataclass(frozen=True)
class RegistrationCode:
    code_id: UUID
    match_id: UUID


# Fake repositories.
ATTACKER = UUID(int=0xA)
VICTIM = UUID(int=0xB)

ATTACKER_MATCH = Match(id=uuid4(), owner_id=ATTACKER)
VICTIM_MATCH = Match(id=uuid4(), owner_id=VICTIM)
ATTACKER_CODE = RegistrationCode(code_id=uuid4(), match_id=ATTACKER_MATCH.id)

CODES = {ATTACKER_CODE.code_id: ATTACKER_CODE}
MATCHES = {ATTACKER_MATCH.id: ATTACKER_MATCH, VICTIM_MATCH.id: VICTIM_MATCH}


async def load_match_from_code(info: Info[Any, Any], kwargs: Mapping[str, Any]) -> Match | None:
    """Walk code_id -> match_id -> Match from authoritative sources.

    The ``match_id`` kwarg, if present, is IGNORED by design -- the
    loader looks up the code, then walks to the match. Attacker-supplied
    ``match_id`` is never consulted.
    """
    del info
    raw_code = kwargs.get("code_id")
    if raw_code is None:
        return None
    try:
        code_id = UUID(str(raw_code))
    except (ValueError, TypeError):
        return None
    code = CODES.get(code_id)
    if code is None:
        return None
    return MATCHES.get(code.match_id)


class _Ctx:
    def __init__(self, actor_id: UUID) -> None:
        self.actor = Actor(user_id=actor_id)
        self.principal_loader_calls = 0


def _principal_from_ctx(info: Info[Any, Any]) -> Principal[Actor, str]:
    ctx: _Ctx = info.context
    ctx.principal_loader_calls += 1
    return Principal(actor=ctx.actor, entitlements=Entitlements.empty())


def _build_schema() -> strawberry.Schema:
    engine: PolicyEngine[Principal[Actor, str], Action, Match] = PolicyEngine()

    @engine.policy(action=Action.REGISTER, subject_type=Match)
    def can_register(
        p: Principal[Actor, str],
        s: Match,
    ) -> Decision:
        if p.actor.user_id == s.owner_id:
            return ALLOW
        return deny("not_match_owner")

    @strawberry.type
    class Mutation:
        @strawberry.mutation(
            extensions=[
                policy_guard(
                    engine=engine,
                    principal_loader=_principal_from_ctx,
                    action=Action.REGISTER,
                    subject_type=Match,
                    load_subject=load_match_from_code,
                )
            ],
        )
        async def register(
            self,
            code_id: strawberry.ID,
            match_id: strawberry.ID,
        ) -> str:
            del code_id, match_id
            return "registered"

    @strawberry.type
    class Query:
        @strawberry.field
        def hello(self) -> str:
            return "world"

    return strawberry.Schema(query=Query, mutation=Mutation)


class TestIndirectIdentifierIDOR:
    def test_attacker_match_id_does_not_influence_decision(self) -> None:
        schema = _build_schema()
        attacker_ctx = _Ctx(actor_id=ATTACKER)

        # Round 1: attacker supplies their own code AND their own match.
        result_legit = asyncio.run(
            schema.execute(
                f'''mutation {{
                    register(codeId: "{ATTACKER_CODE.code_id}",
                             matchId: "{ATTACKER_MATCH.id}")
                }}''',
                context_value=attacker_ctx,
            )
        )

        # Round 2: attacker supplies their own code BUT a victim's match id.
        # The loader walks code -> match (attacker's own match), and the
        # match_id arg is ignored. Result MUST be identical to round 1.
        attacker_ctx2 = _Ctx(actor_id=ATTACKER)
        result_attack = asyncio.run(
            schema.execute(
                f'''mutation {{
                    register(codeId: "{ATTACKER_CODE.code_id}",
                             matchId: "{VICTIM_MATCH.id}")
                }}''',
                context_value=attacker_ctx2,
            )
        )

        assert_that(result_legit.data).is_equal_to(result_attack.data)
        assert_that(result_legit.errors).is_equal_to(result_attack.errors)
        # Both should succeed (the code is attacker's own).
        assert_that(result_legit.data).is_equal_to({"register": "registered"})
