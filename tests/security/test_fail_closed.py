"""Fail-closed security tests.

The engine MUST never raise from decide() or adecide() -- every error path
collapses to Decision(allowed=False, reason=...).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that
from hypothesis import given, settings
from hypothesis import strategies as st

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"
    MANAGE = "manage"


@dataclass(frozen=True)
class _Subject:
    payload: str


class TestFailClosed:
    def test_random_unregistered_pairs_all_deny(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        for i in range(1000):
            d = engine.decide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(payload=f"s-{i}"),
            )
            assert_that(d.allowed).described_as(f"iter {i}").is_false()
            assert_that(d.reason).is_equal_to("policy_not_registered")

    def test_every_exception_flavor_becomes_policy_error(self) -> None:
        # NOTE: asyncio.CancelledError, KeyboardInterrupt, and SystemExit
        # derive from BaseException (not Exception) and MUST propagate so
        # task cancellation, Ctrl-C, and sys.exit() are not silently
        # swallowed. The engine catches Exception only -- by design.
        exception_classes: list[type[Exception]] = [
            RuntimeError,
            ValueError,
            TypeError,
            LookupError,
            AttributeError,
            KeyError,
            ArithmeticError,
            OSError,
        ]

        for exc_cls in exception_classes:
            engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

            def _broken(
                _p: object,
                _s: _Subject,
                *,
                _exc: type[Exception] = exc_cls,
            ) -> Decision:
                raise _exc("synthetic")

            engine.replace_policy(
                action=_Action.READ,
                subject_type=_Subject,
            )(_broken)

            d = engine.decide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(payload="x"),
            )
            assert_that(d.allowed).described_as(exc_cls.__name__).is_false()
            assert_that(d.reason).described_as(exc_cls.__name__).is_equal_to("policy_error")

    def test_base_exceptions_propagate(self) -> None:
        # By design: asyncio.CancelledError, KeyboardInterrupt, and
        # SystemExit propagate out of decide() so they reach the runtime's
        # cancellation / signal-handling machinery. This is the inverse of
        # the test above: any subclass of BaseException that is NOT a
        # subclass of Exception MUST escape decide().
        base_exception_classes: list[type[BaseException]] = [
            asyncio.CancelledError,
            KeyboardInterrupt,
            SystemExit,
        ]
        for exc_cls in base_exception_classes:
            engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

            def _broken(
                _p: object,
                _s: _Subject,
                *,
                _exc: type[BaseException] = exc_cls,
            ) -> Decision:
                raise _exc("synthetic")

            engine.replace_policy(
                action=_Action.READ,
                subject_type=_Subject,
            )(_broken)

            propagated = False
            try:
                engine.decide(
                    principal=object(),
                    action=_Action.READ,
                    subject=_Subject(payload="x"),
                )
            except exc_cls:
                propagated = True
            except BaseException:  # noqa: BLE001 -- pinpoint exact class
                propagated = False
            assert_that(propagated).described_as(exc_cls.__name__).is_true()


class TestDecisionTotalityHypothesis:
    """Hypothesis fuzz: decide() and adecide() must never raise."""

    @given(
        action_idx=st.integers(min_value=0, max_value=len(list(_Action)) - 1),
        payload=st.text(max_size=50),
        is_registered=st.booleans(),
        policy_raises=st.booleans(),
    )
    @settings(max_examples=200, deadline=None)
    def test_decide_is_total(
        self,
        action_idx: int,
        payload: str,
        is_registered: bool,
        policy_raises: bool,
    ) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        action = list(_Action)[action_idx]

        if is_registered:
            if policy_raises:

                def _raises(_p: object, _s: _Subject) -> Decision:
                    raise RuntimeError("synthetic")

                engine.policy(action=action, subject_type=_Subject)(_raises)
            else:

                def _allow(_p: object, _s: _Subject) -> Decision:
                    return ALLOW

                engine.policy(action=action, subject_type=_Subject)(_allow)

        d = engine.decide(
            principal=object(),
            action=action,
            subject=_Subject(payload=payload),
        )
        # The only invariant Hypothesis cares about: no exception escaped.
        assert_that(isinstance(d, Decision)).is_true()
        assert_that(isinstance(d.allowed, bool)).is_true()

    @given(
        action_idx=st.integers(min_value=0, max_value=len(list(_Action)) - 1),
        payload=st.text(max_size=50),
        is_registered=st.booleans(),
        policy_raises=st.booleans(),
    )
    @settings(max_examples=200, deadline=None)
    def test_adecide_is_total(
        self,
        action_idx: int,
        payload: str,
        is_registered: bool,
        policy_raises: bool,
    ) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        action = list(_Action)[action_idx]

        if is_registered:
            if policy_raises:

                def _raises(_p: object, _s: _Subject) -> Decision:
                    raise RuntimeError("synthetic")

                engine.policy(action=action, subject_type=_Subject)(_raises)
            else:

                def _allow(_p: object, _s: _Subject) -> Decision:
                    return ALLOW

                engine.policy(action=action, subject_type=_Subject)(_allow)

        d = asyncio.run(
            engine.adecide(
                principal=object(),
                action=action,
                subject=_Subject(payload=payload),
            )
        )
        assert_that(isinstance(d, Decision)).is_true()
        assert_that(isinstance(d.allowed, bool)).is_true()
