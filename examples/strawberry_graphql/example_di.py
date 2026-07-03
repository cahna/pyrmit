"""DI-style example: guard pulling its engine + principal from the request context.

This mirrors how an application wired with FastAPI + Strawberry would
supply both the policy engine *and* the principal via dependency
injection rather than as module-level globals. The schema and field
decorators contain *no* reference to either: ``Lazy(...)`` defers
engine resolution to request time, and a plain principal-loader
callable pulls the actor off the per-request Strawberry context that
FastAPI built from its DI providers.

The two cross-cutting deps (engine + principal_loader) are bundled in
a :class:`PolicyGuardFactory` so each guarded field only restates what
varies (action, subject type, subject loader).

Run::

    uv run python examples/strawberry_graphql/example_di.py

The driver simulates several requests with different actors against
the same schema. Each request constructs its own context carrying the
(app-scoped) engine and the per-request actor.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import lru_cache
from typing import Any

import strawberry
from graphql import GraphQLError
from strawberry.fastapi import BaseContext
from strawberry.types import ExecutionContext, Info

from pyrmit.adapters.strawberry import (
    PermissionDenied,
    PolicyGuardFactory,
    ResourceNotFound,
)
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.lazy import Lazy
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Actor:
    user_id: int
    is_admin: bool


@dataclass(frozen=True)
class Article:
    id: int
    owner_id: int
    is_published: bool
    title: str


ARTICLES: dict[int, Article] = {
    1: Article(id=1, owner_id=42, is_published=True, title="Hello, world"),
    2: Article(id=2, owner_id=42, is_published=False, title="Draft post"),
}


# ---------------------------------------------------------------------------
# "DI providers" -- in a real FastAPI app these would be `Annotated[..., Depends(...)]`
# providers wired into the Strawberry context_getter. Here they are plain
# functions decorated with lru_cache(1) to mimic app-scoped singletons.
# ---------------------------------------------------------------------------


@lru_cache(maxsize=1)
def provide_engine() -> PolicyEngine[Principal[Actor, str], Action, Article]:
    """App-scoped engine. Constructed once, reused across requests."""
    engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Article, denial_surface=DenialSurface.NOT_FOUND)
    def _read(principal: Principal[Actor, str], article: Article) -> Decision:
        if principal.actor.is_admin:
            return ALLOW
        if article.is_published:
            return ALLOW
        if article.owner_id == principal.actor.user_id:
            return ALLOW
        return deny("article_unpublished")

    return engine


class RequestContext(BaseContext):
    """Per-request Strawberry context.

    Carries:
      * the app-scoped engine (read via the ``Lazy`` resolver below)
      * the current actor (consumed by the principal loader below)

    In a real FastAPI app this would be returned from the GraphQLRouter
    ``context_getter`` after FastAPI resolved its dependencies.
    """

    def __init__(
        self,
        *,
        authz_engine: PolicyEngine[Principal[Actor, str], Action, Article],
        actor: Actor,
    ) -> None:
        super().__init__()
        self.authz_engine = authz_engine
        self.actor = actor


def build_request_context(actor: Actor) -> RequestContext:
    """Stand-in for FastAPI's ``context_getter`` callable."""
    return RequestContext(authz_engine=provide_engine(), actor=actor)


# ---------------------------------------------------------------------------
# Loader -- already receives Info, so it can pull request-scoped state
# (e.g. an AsyncSession) off the context. Here it just consults a dict.
# ---------------------------------------------------------------------------


async def load_article(info: Info[Any, Any], kwargs: Mapping[str, Any]) -> Article | None:
    del info
    raw = kwargs.get("article_id")
    if raw is None:
        return None
    try:
        article_id = int(raw)
    except (ValueError, TypeError):
        return None
    return ARTICLES.get(article_id)


# ---------------------------------------------------------------------------
# Schema -- note there is NO module-level engine referenced here.
# The Lazy resolver fetches it from the per-request context.
# ---------------------------------------------------------------------------


def _engine_from_ctx(info: Info[Any, Any]) -> PolicyEngine[Principal[Actor, str], Action, Article]:
    # ``info.context`` is Strawberry-Any; assign it to a typed intermediate
    # so the return is concretely typed (``RequestContext.authz_engine`` is
    # already annotated) rather than leaking Any out of the accessor.
    context: RequestContext = info.context
    return context.authz_engine


def _principal_from_ctx(info: Info[Any, Any]) -> Principal[Actor, str]:
    actor: Actor = info.context.actor
    return Principal[Actor, str](actor=actor, entitlements=Entitlements[str].empty())


# Bundle the cross-cutting deps once; every guarded field calls
# ``policy.guard(...)`` without restating engine or principal loader. The
# factory is parameterized over the same (principal, action, subject)
# triple as the engine, so ``policy.guard(action=..., subject_type=...)``
# is type-checked against ``Action`` / ``Article``.
policy: PolicyGuardFactory[Principal[Actor, str], Action, Article] = PolicyGuardFactory(
    engine=Lazy(_engine_from_ctx),
    principal_loader=_principal_from_ctx,
)


@strawberry.type
class ArticleType:
    id: int
    title: str


@strawberry.type
class Query:
    @strawberry.field(
        extensions=[
            policy.guard(
                action=Action.READ,
                subject_type=Article,
                load_subject=load_article,
            )
        ],
    )
    async def article(self, article_id: int) -> ArticleType | None:
        article = ARTICLES.get(article_id)
        if article is None:
            return None
        return ArticleType(id=article.id, title=article.title)


class Schema(strawberry.Schema):
    """Schema that skips logging expected authorization denials.

    Strawberry's default ``process_errors`` logs every GraphQL error with
    a full traceback via the ``strawberry.execution`` logger. Guard
    denials are expected outcomes, not server faults, so they are
    filtered out here; any other error still reaches the default logger.
    """

    def process_errors(
        self,
        errors: list[GraphQLError],
        execution_context: ExecutionContext | None = None,
    ) -> None:
        unexpected = [
            error for error in errors if not isinstance(error.original_error, PermissionDenied | ResourceNotFound)
        ]
        if unexpected:
            super().process_errors(unexpected, execution_context)


SCHEMA = Schema(query=Query)


# ---------------------------------------------------------------------------
# Driver -- simulate two requests with different actors. Each request gets
# its own context, both pointing at the same app-scoped engine.
# ---------------------------------------------------------------------------


async def _run() -> None:
    actors = {
        "admin": Actor(user_id=1, is_admin=True),
        "owner": Actor(user_id=42, is_admin=False),
        "stranger": Actor(user_id=99, is_admin=False),
    }
    query = "{ article(articleId: 2) { id title } }"
    for label, actor in actors.items():
        ctx = build_request_context(actor)
        result = await SCHEMA.execute(query, context_value=ctx)
        print(f"[{label}] data={result.data!r} errors={result.errors!r}")

    # Demonstrate the engine is in fact app-scoped (one instance, two requests).
    print(f"engine id stable across calls: {id(provide_engine()) == id(provide_engine())}")


if __name__ == "__main__":
    asyncio.run(_run())
