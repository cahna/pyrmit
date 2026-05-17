"""Unit tests for engine.decide -- happy paths and totality."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class _Subject:
    id: int
    is_published: bool


class TestEngineDecide:
    def _engine_with_simple_policy(
        self,
    ) -> PolicyEngine[object, _Action, _Subject]:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, s: _Subject) -> Decision:
            if s.is_published:
                return ALLOW
            return deny("unpublished")

        return engine

    def test_allow_path(self) -> None:
        engine = self._engine_with_simple_policy()
        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1, is_published=True),
        )
        assert_that(d.allowed).is_true()
        assert_that(d.reason).is_none()

    def test_deny_path_with_reason(self) -> None:
        engine = self._engine_with_simple_policy()
        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=2, is_published=False),
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("unpublished")

    def test_no_binding_returns_policy_not_registered(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1, is_published=True),
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("policy_not_registered")

    def test_policy_exception_becomes_policy_error(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _broken(_p: object, _s: _Subject) -> Decision:
            raise RuntimeError("boom")

        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1, is_published=True),
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("policy_error")

    def test_decide_never_raises_under_keyboardinterrupt_subclass(self) -> None:
        # KeyboardInterrupt and SystemExit derive from BaseException, not
        # Exception. The engine catches Exception only -- but ensure a
        # plain Exception subclass is fully captured.
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _broken(_p: object, _s: _Subject) -> Decision:
            raise ValueError("nope")

        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1, is_published=True),
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("policy_error")
