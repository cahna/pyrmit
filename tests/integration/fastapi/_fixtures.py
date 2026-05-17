"""Shared FastAPI test fixtures."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID

from fastapi import Request

from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"
    MANAGE = "manage"


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    is_admin: bool


@dataclass(frozen=True)
class Match:
    id: UUID
    owner_id: UUID


_OWNER = UUID(int=1)
_OTHER = UUID(int=2)
EXISTING_MATCH = Match(id=UUID(int=100), owner_id=_OWNER)
MATCHES: dict[UUID, Match] = {EXISTING_MATCH.id: EXISTING_MATCH}


async def load_match(request: Request) -> Match | None:
    """Load a Match by path id; None if the id is unknown."""
    raw: object = request.path_params.get("match_id")
    if raw is None:
        return None
    try:
        match_id = UUID(str(raw))
    except (ValueError, TypeError):
        return None
    return MATCHES.get(match_id)


def make_principal_loader(
    actor: Actor,
) -> Callable[[Request], Awaitable[Principal[Actor, str]]]:
    """Build a get_principal callable returning a fixed actor."""

    async def _loader(_request: Request) -> Principal[Actor, str]:
        return Principal(actor=actor, entitlements=Entitlements.empty())

    return _loader
