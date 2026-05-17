"""Typed policy decisions -- core acceptance scenarios.

Tests the published / unpublished / admin / owner / stranger access
matrix end to end.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from uuid import UUID, uuid4

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Actor:
    user_id: UUID
    is_admin: bool


@dataclass(frozen=True)
class Article:
    id: UUID
    owner_id: UUID
    is_published: bool


def _engine() -> PolicyEngine[Principal[Actor, str], Action, Article]:
    engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine()

    @engine.policy(action=Action.READ, subject_type=Article)
    def can_read(p: Principal[Actor, str], s: Article) -> Decision:
        if s.is_published:
            return ALLOW
        if p.actor.is_admin:
            return ALLOW
        if p.actor.user_id == s.owner_id:
            return ALLOW
        return deny("article_unpublished")

    return engine


def _principal(actor: Actor) -> Principal[Actor, str]:
    return Principal(actor=actor, entitlements=Entitlements.empty())


class TestUserStory1AcceptanceMatrix:
    def test_published_article_visible_to_stranger(self) -> None:
        engine = _engine()
        stranger = _principal(Actor(user_id=uuid4(), is_admin=False))
        article = Article(id=uuid4(), owner_id=uuid4(), is_published=True)
        d = engine.decide(
            principal=stranger,
            action=Action.READ,
            subject=article,
        )
        assert_that(d.allowed).is_true()

    def test_unpublished_article_hidden_from_stranger(self) -> None:
        engine = _engine()
        stranger = _principal(Actor(user_id=uuid4(), is_admin=False))
        article = Article(id=uuid4(), owner_id=uuid4(), is_published=False)
        d = engine.decide(
            principal=stranger,
            action=Action.READ,
            subject=article,
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("article_unpublished")

    def test_owner_sees_their_unpublished_article(self) -> None:
        engine = _engine()
        owner_id = uuid4()
        owner = _principal(Actor(user_id=owner_id, is_admin=False))
        article = Article(id=uuid4(), owner_id=owner_id, is_published=False)
        d = engine.decide(
            principal=owner,
            action=Action.READ,
            subject=article,
        )
        assert_that(d.allowed).is_true()

    def test_admin_sees_anyones_unpublished_article(self) -> None:
        engine = _engine()
        admin = _principal(Actor(user_id=uuid4(), is_admin=True))
        article = Article(id=uuid4(), owner_id=uuid4(), is_published=False)
        d = engine.decide(
            principal=admin,
            action=Action.READ,
            subject=article,
        )
        assert_that(d.allowed).is_true()
