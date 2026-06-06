"""adecide audit dispatch: outcome-filter defaults + sync no-audit."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.audit import AuditOutcome
from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestAuditDispatch:
    def test_deny_audited_by_default(self) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(audit=store)

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return deny("nope")

        asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        entries = store.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].outcome).is_equal_to(AuditOutcome.DENIED)
        assert_that(entries[0].reason).is_equal_to("nope")

    def test_allow_not_audited_by_default(self) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(audit=store)

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        assert_that(store.entries()).is_empty()

    def test_allow_audited_when_opted_in(self) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        entries = store.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].outcome).is_equal_to(AuditOutcome.ALLOWED)

    def test_policy_exception_audited_as_error(self) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(audit=store)

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _broken(_p: object, _s: _Subject) -> Decision:
            raise RuntimeError("boom")

        asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        entries = store.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].outcome).is_equal_to(AuditOutcome.ERROR)
        assert_that(entries[0].reason).is_equal_to("policy_error")

    def test_sync_decide_emits_no_audit(self) -> None:
        store = InMemoryAuditStore(capacity=4)
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1),
        )
        # sync path MUST NOT audit.
        assert_that(store.entries()).is_empty()
