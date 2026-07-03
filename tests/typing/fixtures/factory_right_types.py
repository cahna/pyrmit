"""Positive control: a factory used with matching action + subject types.

This fixture MUST type-check cleanly. Run via mypy as a subprocess from
``test_factory_rejects_wrong_types.py``. If this file ever stops
type-checking, the negative fixtures would pass spuriously (mypy choking
on imports rather than on the type mismatch), so the test asserts all
cases together.
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


def _principal_loader(info: Info[object, object]) -> Principal[Actor, str]:
    del info
    return Principal[Actor, str](actor=Actor(user_id=1), entitlements=Entitlements[str].empty())


async def _load_doc(info: Info[object, object], kwargs: Mapping[str, object]) -> Doc | None:
    del info, kwargs
    return Doc(id=1)


async def _load_doc_after(result: object, info: Info[object, object]) -> Doc | None:
    del result, info
    return Doc(id=1)


_engine: PolicyEngine[Principal[Actor, str], Action, Doc] = PolicyEngine()
_factory = PolicyGuardFactory(engine=_engine, principal_loader=_principal_loader)

# Correct action + subject loader element type -> mypy accepts.
_pre = _factory.guard(action=Action.READ, subject_type=Doc, load_subject=_load_doc)
_post = _factory.post_resolution_guard(
    action=Action.READ,
    subject_type=Doc,
    load_subject_after=_load_doc_after,
)
