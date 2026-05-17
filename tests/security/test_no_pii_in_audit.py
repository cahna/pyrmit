"""PII hygiene: no raw actor / subject in audit entries."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from types import MappingProxyType

from assertpy import assert_that

from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.audit import AuditEntry, AuditOutcome
from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Actor:
    """An actor whose repr() includes a marker string the test searches for."""

    secret_email: str = "SECRET-EMAIL-MARKER@example.com"


@dataclass(frozen=True)
class _Subject:
    """A subject whose repr() includes another marker string."""

    secret_payload: str = "SECRET-PAYLOAD-MARKER"


def _serialize_entry(entry: AuditEntry) -> str:
    """Render an AuditEntry to a JSON string for substring scanning."""
    payload = {
        "id": entry.id,
        "timestamp": entry.timestamp.isoformat(),
        "outcome": entry.outcome.value,
        "action": entry.action,
        "subject_type": entry.subject_type,
        "subject_id": entry.subject_id,
        "actor_id": entry.actor_id,
        "reason": entry.reason,
        "denial_surface": entry.denial_surface,
        "request_id": entry.request_id,
        "metadata": dict(entry.metadata),
    }
    return json.dumps(payload)


class TestNoPiiInAudit:
    def test_no_actor_or_subject_repr_in_audit_entries(self) -> None:
        """With no identifier resolvers registered, audit entries MUST
        NOT contain ANY substring from the actor's or subject's repr.
        """
        store = InMemoryAuditStore(capacity=8)
        # No actor_id and no register_subject_id -- the engine has NO
        # explicit identifier resolvers configured.
        engine: PolicyEngine[_Actor, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: _Actor, _s: _Subject) -> Decision:
            return ALLOW

        actor = _Actor()
        subject = _Subject()
        asyncio.run(
            engine.adecide(
                principal=actor,
                action=_Action.READ,
                subject=subject,
            )
        )

        entries = store.entries()
        assert_that(entries).is_length(1)
        entry = entries[0]

        # subject_id and actor_id MUST be None.
        assert_that(entry.subject_id).is_none()
        assert_that(entry.actor_id).is_none()

        # No marker substring appears anywhere in the rendered entry.
        rendered = _serialize_entry(entry)
        assert_that("SECRET-EMAIL-MARKER" in rendered).described_as("actor's secret_email leaked into audit").is_false()
        assert_that("SECRET-PAYLOAD-MARKER" in rendered).described_as(
            "subject's secret_payload leaked into audit"
        ).is_false()

    def test_subject_type_name_is_present_but_no_subject_data(self) -> None:
        store = InMemoryAuditStore(capacity=8)
        engine: PolicyEngine[_Actor, _Action, _Subject] = PolicyEngine(
            audit=store,
            audit_allows=True,
        )

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: _Actor, _s: _Subject) -> Decision:
            return ALLOW

        asyncio.run(
            engine.adecide(
                principal=_Actor(),
                action=_Action.READ,
                subject=_Subject(),
            )
        )

        entry = store.entries()[0]
        # Subject TYPE name is part of audit (intentional).
        assert_that(entry.subject_type).is_equal_to("_Subject")
        # But subject DATA is not.
        rendered = _serialize_entry(entry)
        assert_that("SECRET-PAYLOAD" in rendered).is_false()


# Suppress unused-import warning for MappingProxyType / datetime / UTC -- they
# are kept for any future expansion of this test.
_ = (MappingProxyType, datetime, UTC, AuditOutcome)
