"""Test assertion helpers for the pyrmit policy engine.

Intended for use in `pytest` test bodies that need to verify policy
outcomes. All assertions raise ``AssertionError`` on failure (the
familiar pytest contract); they do NOT return ``Result``.
"""

from __future__ import annotations

from collections.abc import Iterable

from pyrmit.core.audit import AuditEntry, AuditOutcome
from pyrmit.core.engine import PolicyEngine


def assert_allowed[PrincipalT, ActionT, SubjectT](
    engine: PolicyEngine[PrincipalT, ActionT, SubjectT],
    *,
    principal: PrincipalT,
    action: ActionT,
    subject: SubjectT,
) -> None:
    """Assert that ``engine.decide(...)`` returns an allow decision."""
    decision = engine.decide(
        principal=principal,
        action=action,
        subject=subject,
    )
    if not decision.allowed:
        msg = (
            f"expected allow but got deny "
            f"(reason={decision.reason!r}, action={action!r}, "
            f"subject_type={type(subject).__name__!r})"
        )
        raise AssertionError(msg)


def assert_denied[PrincipalT, ActionT, SubjectT](
    engine: PolicyEngine[PrincipalT, ActionT, SubjectT],
    *,
    principal: PrincipalT,
    action: ActionT,
    subject: SubjectT,
    reason: str | None = None,
) -> None:
    """Assert that ``engine.decide(...)`` returns a deny decision.

    Args:
        engine: The policy engine.
        principal: The caller's principal.
        action: The action enum value.
        subject: The subject of the action.
        reason: Optional expected reason. If provided, the assertion also
            checks ``decision.reason == reason``.
    """
    decision = engine.decide(
        principal=principal,
        action=action,
        subject=subject,
    )
    if decision.allowed:
        msg = f"expected deny but got allow (action={action!r}, subject_type={type(subject).__name__!r})"
        raise AssertionError(msg)
    if reason is not None and decision.reason != reason:
        msg = (
            f"expected deny reason={reason!r} but got reason={decision.reason!r} "
            f"(action={action!r}, subject_type={type(subject).__name__!r})"
        )
        raise AssertionError(msg)


def assert_audit_denied(
    entries: Iterable[AuditEntry],
    *,
    reason: str | None = None,
) -> None:
    """Assert that at least one DENIED audit entry exists (optionally by reason)."""
    matches = [e for e in entries if e.outcome == AuditOutcome.DENIED and (reason is None or e.reason == reason)]
    if not matches:
        msg = f"no DENIED audit entry found{f' with reason={reason!r}' if reason else ''}"
        raise AssertionError(msg)


def assert_audit_allowed(
    entries: Iterable[AuditEntry],
) -> None:
    """Assert that at least one ALLOWED audit entry exists."""
    if not any(e.outcome == AuditOutcome.ALLOWED for e in entries):
        raise AssertionError("no ALLOWED audit entry found")
