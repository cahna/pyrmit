"""Strawberry audit metadata via an inline AuditStore stub.

This test MUST NOT depend on the built-in ``InMemoryAuditStore`` so the
Strawberry adapter and the audit-store implementations remain
independently shippable.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

import strawberry
from assertpy import assert_that

from pyrmit.adapters.strawberry import policy_guard
from pyrmit.core.audit import AuditEntry, AuditStore
from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.principal import Principal
from tests.integration.strawberry._fixtures import (
    PUBLISHED_ID,
    Action,
    Actor,
    Article,
    load_article,
    make_ctx,
    principal_from_ctx,
)


class _Capture:
    """Inline AuditStore stub satisfying the Protocol structurally."""

    def __init__(self) -> None:
        self.entries: list[AuditEntry] = []

    async def write(self, entry: AuditEntry) -> None:
        self.entries.append(entry)


class TestAuditMetadata:
    def test_decisions_are_audited_via_inline_store(self) -> None:
        store: AuditStore = _Capture()
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine(
            audit=store,
            audit_allows=True,
            audit_denies=True,
        )

        @engine.policy(action=Action.READ, subject_type=Article)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()

        capture = store
        # narrow: type-narrow the abstract AuditStore to the test stub
        assert isinstance(capture, _Capture)
        assert_that(capture.entries).is_length(1)
        entry = capture.entries[0]
        assert_that(entry.action).is_equal_to("read")
        assert_that(entry.subject_type).is_equal_to("Article")
        assert_that(entry.outcome.value).is_equal_to("allowed")

    def test_adapter_metadata_reaches_audit_entry(self) -> None:
        """Regression: ``policy_guard(metadata=...)`` MUST surface on
        ``AuditEntry.metadata``. Without explicit plumbing the kwarg
        was dead -- accepted by the adapter, never reaching audit.
        """
        store: AuditStore = _Capture()
        engine: PolicyEngine[Principal[Actor, str], Action, Article] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=Action.READ, subject_type=Article)
        def _pol(_p: Principal[Actor, str], _s: Article) -> Decision:
            return ALLOW

        @strawberry.type
        class Query:
            @strawberry.field(
                extensions=[
                    policy_guard(
                        engine=engine,
                        principal_loader=principal_from_ctx,
                        action=Action.READ,
                        subject_type=Article,
                        load_subject=load_article,
                        metadata={"adapter": "strawberry", "field": "article"},
                    )
                ],
            )
            async def article(self, article_id: strawberry.ID) -> str:
                del article_id
                return "ok"

        schema = strawberry.Schema(query=Query)
        ctx = make_ctx(Actor(user_id=uuid4(), is_admin=True))
        result = asyncio.run(
            schema.execute(
                f'{{ article(articleId: "{PUBLISHED_ID}") }}',
                context_value=ctx,
            )
        )
        assert_that(result.errors).is_none()

        capture = store
        # narrow: type-narrow the abstract AuditStore to the test stub
        assert isinstance(capture, _Capture)
        assert_that(capture.entries).is_length(1)
        assert_that(dict(capture.entries[0].metadata)).is_equal_to({
            "adapter": "strawberry",
            "field": "article",
        })
