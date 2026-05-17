"""Property tests for the decision algebra of PolicyEngine.

Hypothesis-driven invariants on ``decide`` / ``adecide``:

  1. A registered policy returning ALLOW or deny never escapes -- the
     engine returns a Decision for every shape of input.
  2. A pair ``(action, subject_type)`` that is NOT registered always
     denies with ``reason="policy_not_registered"``.
  3. A policy that raises ANY ``Exception`` is converted into
     ``Decision(allowed=False, reason="policy_error")``.
  4. Audit dispatch matches the outcome category and respects the
     audit-outcome filters.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from assertpy import assert_that
from hypothesis import given
from hypothesis import strategies as st

from pyrmit.audit.memory import InMemoryAuditStore
from pyrmit.core.audit import AuditOutcome
from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    SHARE = "share"


@dataclass(frozen=True)
class _SubjectA:
    id: int


@dataclass(frozen=True)
class _SubjectB:
    id: int


@dataclass(frozen=True)
class _SubjectC:
    id: int


_SUBJECTS: tuple[type[_SubjectA] | type[_SubjectB] | type[_SubjectC], ...] = (_SubjectA, _SubjectB, _SubjectC)
_action_st: st.SearchStrategy[_Action] = st.sampled_from(list(_Action))
_subject_type_st: st.SearchStrategy[type[_SubjectA] | type[_SubjectB] | type[_SubjectC]] = st.sampled_from(_SUBJECTS)
_decision_st: st.SearchStrategy[Decision] = st.one_of(
    st.just(ALLOW),
    st.text(min_size=1, max_size=12).map(lambda r: deny(r)),
)


def _mk_subject(subject_type: type[_SubjectA] | type[_SubjectB] | type[_SubjectC], n: int) -> object:
    return subject_type(id=n)


def _mk_principal() -> Principal[str, str]:
    return Principal[str, str](actor="alice", entitlements=Entitlements[str].empty())


class TestRegisteredPolicyNeverEscapes:
    """Property 1: a registered policy returning ALLOW or deny never raises out of decide."""

    @given(action=_action_st, subject_type=_subject_type_st, decision=_decision_st, subject_id=st.integers())
    def test_decide_returns_a_decision_for_every_registered_pair(
        self,
        action: _Action,
        subject_type: type[_SubjectA] | type[_SubjectB] | type[_SubjectC],
        decision: Decision,
        subject_id: int,
    ) -> None:
        engine: PolicyEngine[Principal[str, str], _Action, object] = PolicyEngine()

        # Bind the captured decision into a per-trial policy.
        def _policy(_p: Principal[str, str], _s: object, *, _d: Decision = decision) -> Decision:
            return _d

        engine.policy(action=action, subject_type=cast(type[object], subject_type))(_policy)
        subject = _mk_subject(subject_type, subject_id)
        result = engine.decide(principal=_mk_principal(), action=action, subject=subject)
        # Same decision returned (modulo defensive-copy semantics on detail).
        assert_that(result.allowed).is_equal_to(decision.allowed)
        assert_that(result.reason).is_equal_to(decision.reason)


class TestUnregisteredAlwaysDeniesPolicyNotRegistered:
    """Property 2: any (action, subject_type) not registered yields policy_not_registered."""

    @given(action=_action_st, subject_type=_subject_type_st, subject_id=st.integers())
    def test_unregistered_always_denies_with_canonical_reason(
        self,
        action: _Action,
        subject_type: type[_SubjectA] | type[_SubjectB] | type[_SubjectC],
        subject_id: int,
    ) -> None:
        engine: PolicyEngine[Principal[str, str], _Action, object] = PolicyEngine()
        subject = _mk_subject(subject_type, subject_id)
        result = engine.decide(principal=_mk_principal(), action=action, subject=subject)
        assert_that(result.allowed).is_false()
        assert_that(result.reason).is_equal_to("policy_not_registered")


class TestPolicyExceptionBecomesDenyPolicyError:
    """Property 3: a policy raising ANY Exception is converted to policy_error."""

    @given(
        action=_action_st,
        subject_type=_subject_type_st,
        exc_message=st.text(max_size=24),
        subject_id=st.integers(),
    )
    def test_any_exception_in_policy_becomes_policy_error(
        self,
        action: _Action,
        subject_type: type[_SubjectA] | type[_SubjectB] | type[_SubjectC],
        exc_message: str,
        subject_id: int,
    ) -> None:
        engine: PolicyEngine[Principal[str, str], _Action, object] = PolicyEngine()

        def _raises(_p: Principal[str, str], _s: object) -> Decision:
            raise RuntimeError(exc_message)

        engine.policy(action=action, subject_type=cast(type[object], subject_type))(_raises)
        subject = _mk_subject(subject_type, subject_id)
        result = engine.decide(principal=_mk_principal(), action=action, subject=subject)
        assert_that(result.allowed).is_false()
        assert_that(result.reason).is_equal_to("policy_error")


class TestAuditEmissionMatchesOutcome:
    """Property 4: with audit on, error outcomes always emit exactly one ERROR audit entry."""

    @given(action=_action_st, subject_type=_subject_type_st, subject_id=st.integers())
    def test_policy_error_emits_exactly_one_error_audit_entry(
        self,
        action: _Action,
        subject_type: type[_SubjectA] | type[_SubjectB] | type[_SubjectC],
        subject_id: int,
    ) -> None:
        store = InMemoryAuditStore()
        engine: PolicyEngine[Principal[str, str], _Action, object] = PolicyEngine(
            audit=store,
            audit_errors=True,
            audit_denies=False,
            audit_allows=False,
        )

        def _raises(_p: Principal[str, str], _s: object) -> Decision:
            raise RuntimeError("boom")

        engine.policy(action=action, subject_type=cast(type[object], subject_type))(_raises)
        subject = _mk_subject(subject_type, subject_id)
        result = asyncio.run(engine.adecide(principal=_mk_principal(), action=action, subject=subject))
        assert_that(result.reason).is_equal_to("policy_error")
        entries = store.entries()
        assert_that(entries).is_length(1)
        assert_that(entries[0].outcome).is_equal_to(AuditOutcome.ERROR)
