"""Negative case: policy decorated with one subject_type but signature uses another.

This fixture MUST fail mypy --strict with an arg-type error citing the
mismatch between MatchSubject (declared via subject_type) and ClubSubject
(declared via the function signature). The subprocess-mypy test in
``test_decorator_rejects_wrong_subject.py`` asserts non-zero exit and an
arg-type error.

If a future refactor of ``engine.policy`` widens this contract (e.g. makes
ST cast-erased to ``object``), this negative test will start passing
spuriously -- which is the bug the test guards against.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
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


# Intentional mismatch: subject_type=MatchSubject, but the function accepts
# ClubSubject. mypy MUST reject this.
@_engine.policy(action=Action.READ, subject_type=MatchSubject)
def _wrong_subject_policy(_p: Principal[Actor, str], _s: ClubSubject) -> Decision:
    return ALLOW
