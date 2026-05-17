"""Runnable FastAPI example: ``require_policy`` protecting a route.

Run::

    uv run python examples/fastapi/example.py

Demonstrates three calls against the same app with different actors
(supplied via an ``X-Actor`` header for example simplicity): admin
(200), owner of an unpublished article (200), stranger (404). The
``Article`` model has an ``is_published`` flag; published articles are
readable by anyone, unpublished ones only by the owner or an admin.
The denial surfaces as 404 NOT_FOUND so unpublished articles look
identical to articles that don't exist.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import httpx
from fastapi import Depends, FastAPI, Request

from pyrmit.adapters.fastapi import require_policy
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
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

ACTORS: dict[str, Actor] = {
    "admin": Actor(user_id=1, is_admin=True),
    "owner": Actor(user_id=42, is_admin=False),
    "stranger": Actor(user_id=99, is_admin=False),
}


# ---------------------------------------------------------------------------
# Engine setup
# ---------------------------------------------------------------------------

engine: PolicyEngine[Principal[Actor], Action, Article] = PolicyEngine()


@engine.policy(action=Action.READ, subject_type=Article, denial_surface=DenialSurface.NOT_FOUND)
def can_read(principal: Principal[Actor], article: Article) -> Decision:
    """Admin and owner always read; anyone reads a published article."""
    if principal.actor.is_admin:
        return ALLOW
    if article.is_published:
        return ALLOW
    if article.owner_id == principal.actor.user_id:
        return ALLOW
    return deny("article_unpublished")


async def get_principal(request: Request) -> Principal[Actor]:
    """Resolve the per-request principal from the X-Actor header.

    Real applications would inspect a JWT / session cookie / API key.
    """
    label = request.headers.get("x-actor", "stranger")
    actor = ACTORS.get(label, ACTORS["stranger"])
    return Principal[Actor](actor=actor, entitlements=Entitlements.empty())


async def load_article_from_path(request: Request) -> Article | None:
    """Resolve the ``{article_id}`` path parameter to an Article."""
    raw: Any = request.path_params.get("article_id")
    try:
        article_id = int(raw)
    except (ValueError, TypeError):
        return None
    return ARTICLES.get(article_id)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def build_app() -> FastAPI:
    """Construct the FastAPI app; factored out so the test can import it."""
    app = FastAPI()

    @app.get("/articles/{article_id}")
    async def get_article(
        article_id: int,
        _: None = Depends(
            require_policy(
                engine=engine,
                action=Action.READ,
                subject_type=Article,
                load_subject=load_article_from_path,
                get_principal=get_principal,
            ),
        ),
    ) -> dict[str, Any]:
        article = ARTICLES[article_id]  # safe: require_policy resolved + decided
        return {"id": article.id, "title": article.title}

    return app


APP = build_app()


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


async def _run() -> None:
    transport = httpx.ASGITransport(app=APP)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as client:
        for label in ("admin", "owner", "stranger"):
            resp = await client.get("/articles/2", headers={"x-actor": label})
            print(f"[{label}] status={resp.status_code} body={resp.text}")


if __name__ == "__main__":
    asyncio.run(_run())
