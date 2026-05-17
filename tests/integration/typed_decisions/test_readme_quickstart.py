"""The README quickstart, verbatim, as a real test.

If you change ``README.md`` you MUST update this file too; the two are
intentionally a pair so the documented first impression cannot rot.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit import ALLOW, Decision, Entitlements, PolicyEngine, Principal, deny


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


engine: PolicyEngine[Principal[Actor], Action, Article] = PolicyEngine()


@engine.policy(action=Action.READ, subject_type=Article)
def can_read_article(principal: Principal[Actor], article: Article) -> Decision:
    if principal.actor.is_admin:
        return ALLOW
    if article.is_published:
        return ALLOW
    if article.owner_id == principal.actor.user_id:
        return ALLOW
    return deny("article_unpublished")


class TestReadmeQuickstart:
    def test_unpublished_article_denies_with_stable_reason(self) -> None:
        alice = Principal[Actor](
            actor=Actor(user_id=42, is_admin=False),
            entitlements=Entitlements.empty(),
        )
        hidden = Article(id=1, owner_id=99, is_published=False)
        decision = engine.decide(principal=alice, action=Action.READ, subject=hidden)
        assert_that(decision.allowed).is_false()
        assert_that(decision.reason).is_equal_to("article_unpublished")

    def test_published_article_allows(self) -> None:
        alice = Principal[Actor](
            actor=Actor(user_id=42, is_admin=False),
            entitlements=Entitlements.empty(),
        )
        public = Article(id=2, owner_id=99, is_published=True)
        decision = engine.decide(principal=alice, action=Action.READ, subject=public)
        assert_that(decision.allowed).is_true()

    def test_owner_can_read_their_own_unpublished_article(self) -> None:
        owner = Principal[Actor](
            actor=Actor(user_id=99, is_admin=False),
            entitlements=Entitlements.empty(),
        )
        hidden = Article(id=3, owner_id=99, is_published=False)
        decision = engine.decide(principal=owner, action=Action.READ, subject=hidden)
        assert_that(decision.allowed).is_true()

    def test_admin_can_read_anything(self) -> None:
        admin = Principal[Actor](
            actor=Actor(user_id=1, is_admin=True),
            entitlements=Entitlements.empty(),
        )
        hidden = Article(id=4, owner_id=99, is_published=False)
        decision = engine.decide(principal=admin, action=Action.READ, subject=hidden)
        assert_that(decision.allowed).is_true()
