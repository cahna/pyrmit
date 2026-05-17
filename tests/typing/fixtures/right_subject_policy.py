"""Positive control: policy whose function signature matches subject_type.

This fixture MUST type-check cleanly. Run via mypy as a subprocess from
``test_decorator_rejects_wrong_subject.py``. If this file ever stops
type-checking, the negative test would pass spuriously (mypy choking on
imports rather than on the policy mismatch), so the test asserts both
together.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Actor:
    user_id: int


@dataclass(frozen=True)
class MatchSubject:
    id: int


@dataclass(frozen=True)
class ClubSubject:
    id: int


_engine: PolicyEngine[Principal[Actor, str], Action, object] = PolicyEngine()


@_engine.policy(action=Action.READ, subject_type=MatchSubject)
def _match_policy(_p: Principal[Actor, str], _s: MatchSubject) -> Decision:
    return ALLOW


_actor = Actor(user_id=1)
_principal = Principal[Actor, str](actor=_actor, entitlements=Entitlements[str].empty())
_subject = MatchSubject(id=1)
_decision = _engine.decide(principal=_principal, action=Action.READ, subject=_subject)
