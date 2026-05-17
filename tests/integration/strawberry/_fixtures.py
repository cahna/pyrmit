"""Shared fixtures for the Strawberry adapter integration tests.

We construct a single domain (Article + Actor) and reuse it across the
pre/post-resolution / forbidden / null / not_found / IDOR / inactive
scenarios. Each test builds its own engine and schema on top.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from strawberry.types import Info

from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"
    READ_FIELD = "read_field"


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    is_admin: bool


@dataclass(frozen=True)
class Article:
    """The domain subject the engine decides against."""

    id: UUID
    owner_id: UUID
    is_published: bool
    is_active: bool = True


def make_principal(actor: Actor) -> Principal[Actor, str]:
    return Principal(actor=actor, entitlements=Entitlements.empty())


# Repository: maps article id -> Article, OR None when "doesn't exist".
ARTICLES: dict[UUID, Article] = {}
_FIXED_OWNER = UUID(int=42)
PUBLISHED_ID = uuid4()
UNPUBLISHED_ID = uuid4()
INACTIVE_ID = uuid4()
ARTICLES[PUBLISHED_ID] = Article(
    id=PUBLISHED_ID,
    owner_id=_FIXED_OWNER,
    is_published=True,
    is_active=True,
)
ARTICLES[UNPUBLISHED_ID] = Article(
    id=UNPUBLISHED_ID,
    owner_id=_FIXED_OWNER,
    is_published=False,
    is_active=True,
)
ARTICLES[INACTIVE_ID] = Article(
    id=INACTIVE_ID,
    owner_id=_FIXED_OWNER,
    is_published=True,
    is_active=False,
)


class StubContext:
    """Strawberry context carrying the principal directly.

    The guard pulls the principal via the ``principal_from_ctx`` loader
    below; ``principal_loader_calls`` is bumped on each call so tests
    can assert the per-request caching behavior.
    """

    def __init__(self, principal: Principal[Actor, str]) -> None:
        self.principal = principal
        self.principal_loader_calls = 0


def make_ctx(actor: Actor) -> StubContext:
    return StubContext(make_principal(actor))


def principal_from_ctx(info: Info[Any, Any]) -> Principal[Actor, str]:
    """Loader pulling the principal off a ``StubContext``; counts invocations."""
    ctx: StubContext = info.context
    ctx.principal_loader_calls += 1
    return ctx.principal


def reset_inactive_id(new: UUID) -> None:
    """Allow tests that want a distinct inactive id to register one."""
    ARTICLES[new] = Article(
        id=new,
        owner_id=_FIXED_OWNER,
        is_published=True,
        is_active=False,
    )


# Catch-all helper so tests don't have to repeat type hints constantly.
async def load_article(info: Info[Any, Any], kwargs: Mapping[str, Any]) -> Article | None:
    """Load an Article by id; return None if the id is unknown."""
    del info
    raw = kwargs.get("article_id")
    if raw is None:
        return None
    try:
        article_id = UUID(str(raw))
    except (ValueError, TypeError):
        return None
    return ARTICLES.get(article_id)
