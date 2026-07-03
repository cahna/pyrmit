"""Negative case: a subject loader whose element type mismatches subject_type.

``subject_type=Doc`` pins the guard's ``ST`` to ``Doc``; a ``load_subject``
that resolves to ``Wrong | None`` MUST fail mypy --strict with an arg-type
error. If a future refactor cast-erases the loaders' subject type to
``Any`` this fixture would start type-checking -- the regression the
subprocess-mypy test guards against.
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


@dataclass(frozen=True)
class Actor:
    user_id: int


@dataclass(frozen=True)
class Doc:
    id: int


@dataclass(frozen=True)
class Wrong:
    id: int


def _principal_loader(info: Info[object, object]) -> Principal[Actor, str]:
    del info
    return Principal[Actor, str](actor=Actor(user_id=1), entitlements=Entitlements[str].empty())


async def _load_wrong(info: Info[object, object], kwargs: Mapping[str, object]) -> Wrong | None:
    del info, kwargs
    return Wrong(id=1)


_engine: PolicyEngine[Principal[Actor, str], Action, Doc] = PolicyEngine()
_factory = PolicyGuardFactory(engine=_engine, principal_loader=_principal_loader)

# subject_type=Doc pins ST=Doc, but load_subject resolves to Wrong | None.
# mypy MUST reject the mismatched loader.
_pre = _factory.guard(action=Action.READ, subject_type=Doc, load_subject=_load_wrong)
