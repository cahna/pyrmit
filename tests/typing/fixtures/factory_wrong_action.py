"""Negative case: guard called with an action of the wrong enum type.

The factory is parameterized (via its engine) over ``Action``; passing a
value of an unrelated enum (``OtherEnum``) to ``guard(action=...)`` MUST
fail mypy --strict with an arg-type error. If a future refactor widens
``ActionT`` back to ``Any`` this fixture would start type-checking, which
is exactly the regression the subprocess-mypy test guards against.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from strawberry.types import Info

from pyrmit.adapters.strawberry import PolicyGuardFactory
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"


class OtherEnum(StrEnum):
    X = "x"


@dataclass(frozen=True)
class Actor:
    user_id: int


@dataclass(frozen=True)
class Doc:
    id: int


def _principal_loader(info: Info[object, object]) -> Principal[Actor, str]:
    del info
    return Principal[Actor, str](actor=Actor(user_id=1), entitlements=Entitlements[str].empty())


async def _load_doc(info: Info[object, object], kwargs: Mapping[str, object]) -> Doc | None:
    del info, kwargs
    return Doc(id=1)


_engine: PolicyEngine[Principal[Actor, str], Action, Doc] = PolicyEngine()
_factory = PolicyGuardFactory(engine=_engine, principal_loader=_principal_loader)

# Wrong action enum type: ActionT is Action, not OtherEnum. mypy MUST reject.
_pre = _factory.guard(action=OtherEnum.X, subject_type=Doc, load_subject=_load_doc)
