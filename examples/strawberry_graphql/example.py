"""Runnable Strawberry example: multiple subject types and nested guards.

Run::

    uv run python examples/strawberry_graphql/example.py

A single ``PolicyEngine`` governs two subject types -- ``Article`` and
``User`` -- declared as a PEP 695 union alias (``type Subject = Article |
User``) and enforced at registration time via ``subject_base``. The
schema nests an ``author`` field under ``article``, demonstrating:

* ``load_subject`` -- root field whose subject comes from field
  arguments (``Query.article``);
* ``load_subject_from_source`` -- nested fields whose subject comes
  from the parent value (``ArticleType.author``, ``AuthorType.email``);
* all three denial surfaces side by side:

  - ``NOT_FOUND`` on ``(READ, Article)``: strangers cannot learn that
    an unpublished article exists;
  - ``FORBIDDEN`` (the default) on ``(READ, User)``: the author's
    public profile is open here, but the binding must still exist --
    a missing policy fails closed with ``policy_not_registered``;
  - ``NULL`` on ``(READ_CONTACT, User)``: the owner or an admin sees
    ``email``; everyone else gets ``email: null`` with **no error**,
    so an unauthorized caller cannot distinguish "no email on file"
    from "not allowed to see it".

The driver runs the same nested query as admin (sees everything), the
article owner (sees their own email), and a stranger (published article
visible but email silently null; draft article surfaces NOT_FOUND).

The schema is wired through a :class:`PolicyGuardFactory` so the engine
and principal loader are named once; each guarded field calls
``factory.guard(...)``.
"""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
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
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"
    READ_CONTACT = "read_contact"


@dataclass(frozen=True)
class Actor:
    user_id: int
    is_admin: bool


@dataclass(frozen=True)
class User:
    id: int
    name: str
    email: str


@dataclass(frozen=True)
class Article:
    id: int
    owner_id: int
    is_published: bool
    title: str


# The engine's subject parameter is the union of every guarded domain
# type. ``subject_base=Subject`` (below) makes the engine reject a
# registration against any class outside this union at startup.
type Subject = Article | User


USERS: dict[int, User] = {
    42: User(id=42, name="Ada Lovelace", email="ada@example.com"),
}

ARTICLES: dict[int, Article] = {
    1: Article(id=1, owner_id=42, is_published=True, title="Hello, world"),
    2: Article(id=2, owner_id=42, is_published=False, title="Draft post"),
}


class Context(BaseContext):
    """Strawberry context carrying the current actor.

    The guard reads the principal via the module-level ``load_principal``
    loader, which pulls the actor off this context. In a real FastAPI app
    this would be returned from the GraphQLRouter ``context_getter``.
    """

    def __init__(self, actor: Actor) -> None:
        super().__init__()
        self.actor = actor


# ---------------------------------------------------------------------------
# Engine setup -- one engine, two subject types, three denial surfaces.
# ---------------------------------------------------------------------------

engine: PolicyEngine[Principal[Actor, str], Action, Subject] = PolicyEngine(
    subject_base=Subject,
)


@engine.policy(action=Action.READ, subject_type=Article, denial_surface=DenialSurface.NOT_FOUND)
def can_read_article(principal: Principal[Actor, str], article: Article) -> Decision:
    """Admin and owner always read; anyone reads a published article.

    NOT_FOUND surface: a denied stranger cannot tell whether the
    article exists at all.
    """
    if principal.actor.is_admin:
        return ALLOW
    if article.is_published:
        return ALLOW
    if article.owner_id == principal.actor.user_id:
        return ALLOW
    return deny("article_unpublished")


@engine.policy(action=Action.READ, subject_type=User)
def can_read_user(principal: Principal[Actor, str], user: User) -> Decision:
    """Anyone may read an author's public profile (name).

    Always-allow is still worth registering: the engine fails closed,
    so without this binding every ``author`` field would deny with
    ``policy_not_registered``. The default FORBIDDEN surface applies
    if a future rule ever denies here.
    """
    del principal, user
    return ALLOW


@engine.policy(action=Action.READ_CONTACT, subject_type=User, denial_surface=DenialSurface.NULL)
def can_read_user_contact(principal: Principal[Actor, str], user: User) -> Decision:
    """Only the user themself or an admin may see contact details.

    NULL surface: everyone else receives ``email: null`` with no error
    in the response -- silent redaction rather than a visible denial.
    """
    if principal.actor.is_admin:
        return ALLOW
    if user.id == principal.actor.user_id:
        return ALLOW
    return deny("contact_private")


def load_principal(info: Info[Any, Any]) -> Principal[Actor, str]:
    """Build the per-request principal from the context's actor."""
    actor: Actor = info.context.actor
    return Principal[Actor, str](actor=actor, entitlements=Entitlements[str].empty())


# ---------------------------------------------------------------------------
# Subject loaders -- one per guard phase in use.
# ---------------------------------------------------------------------------


async def load_article(info: Info[Any, Any], kwargs: Mapping[str, Any]) -> Article | None:
    """Pre-resolution loader: resolve the requested article by id from kwargs."""
    del info
    raw = kwargs.get("article_id")
    if raw is None:
        return None
    try:
        article_id = int(raw)
    except (ValueError, TypeError):
        return None
    return ARTICLES.get(article_id)


async def load_author_from_article(source: ArticleType, info: Info[Any, Any]) -> User | None:
    """From-source loader: fetch the author ``User`` keyed by the parent article.

    The parent ``ArticleType`` carries its domain ``owner_id`` in a
    ``strawberry.Private`` field, so the guard can resolve the subject
    without any field arguments. In a real app this lookup would hit a
    DataLoader or session.
    """
    del info
    return USERS.get(source.owner_id)


async def load_user_from_author(source: AuthorType, info: Info[Any, Any]) -> User | None:
    """From-source loader: the parent ``AuthorType`` already carries the subject."""
    del info
    return source.user


# Bundle the engine + principal loader once; every guarded field calls
# ``policy.guard(...)`` without restating them.
policy = PolicyGuardFactory(engine=engine, principal_loader=load_principal)


# ---------------------------------------------------------------------------
# Schema -- type definitions live at module scope so Strawberry can resolve
# forward references.
# ---------------------------------------------------------------------------


@strawberry.type
class AuthorType:
    name: str
    # Domain object captured at construction; excluded from the GraphQL
    # schema, consumed by ``load_user_from_author`` and the resolver.
    user: strawberry.Private[User]

    @strawberry.field(
        extensions=[
            policy.guard(
                action=Action.READ_CONTACT,
                subject_type=User,
                load_subject_from_source=load_user_from_author,
            )
        ],
    )
    async def email(self) -> str | None:
        """Guarded by the NULL surface: denied callers see ``null``, not an error."""
        return self.user.email


@strawberry.type
class ArticleType:
    id: int
    title: str
    # Domain key captured at construction for the nested author guard.
    owner_id: strawberry.Private[int]

    @strawberry.field(
        extensions=[
            policy.guard(
                action=Action.READ,
                subject_type=User,
                load_subject_from_source=load_author_from_article,
            )
        ],
    )
    async def author(self) -> AuthorType | None:
        """Nested field guarded against the *author* subject, not the article."""
        user = USERS.get(self.owner_id)
        if user is None:
            return None
        return AuthorType(name=user.name, user=user)


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
        """Field-level guard runs before this resolver."""
        article = ARTICLES.get(article_id)
        if article is None:
            return None
        return ArticleType(id=article.id, title=article.title, owner_id=article.owner_id)


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
# Driver
# ---------------------------------------------------------------------------


async def _run() -> None:
    actors = {
        "admin": Actor(user_id=1, is_admin=True),
        "owner": Actor(user_id=42, is_admin=False),
        "stranger": Actor(user_id=99, is_admin=False),
    }
    scenarios = {
        # Everyone reads the published article; only owner/admin see email.
        "published article": "{ article(articleId: 1) { id title author { name email } } }",
        # Stranger is denied the draft entirely -- via NOT_FOUND.
        "draft article": "{ article(articleId: 2) { id title author { name email } } }",
    }
    for description, query in scenarios.items():
        print(f"-- {description} --")
        for label, actor in actors.items():
            result = await SCHEMA.execute(query, context_value=Context(actor))
            print(f"[{label}] data={result.data!r} errors={result.errors!r}")


if __name__ == "__main__":
    asyncio.run(_run())
