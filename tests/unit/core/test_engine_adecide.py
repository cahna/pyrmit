"""Unit tests for engine.adecide mirroring decide() when audit=None."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, deny
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestEngineAdecide:
    def _build(self) -> PolicyEngine[object, _Action, _Subject]:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, s: _Subject) -> Decision:
            return ALLOW if s.id > 0 else deny("nonpositive")

        return engine

    def test_adecide_allow_path(self) -> None:
        engine = self._build()
        d = asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        assert_that(d.allowed).is_true()

    def test_adecide_deny_path(self) -> None:
        engine = self._build()
        d = asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=0),
            )
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("nonpositive")

    def test_adecide_no_binding_returns_policy_not_registered(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        d = asyncio.run(
            engine.adecide(
                principal=object(),
                action=_Action.READ,
                subject=_Subject(id=1),
            )
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("policy_not_registered")

    def test_adecide_concurrent_invocations(self) -> None:
        engine = self._build()

        async def _run() -> list[Decision]:
            return await asyncio.gather(*[
                engine.adecide(
                    principal=object(),
                    action=_Action.READ,
                    subject=_Subject(id=i),
                )
                for i in range(-5, 5)
            ])

        results = asyncio.run(_run())
        assert_that(results).is_length(10)
        # All decisions should be deterministic and consistent.
        for i, d in enumerate(results):
            expected_id = i - 5
            if expected_id > 0:
                assert_that(d.allowed).described_as(f"id={expected_id}").is_true()
            else:
                assert_that(d.allowed).described_as(f"id={expected_id}").is_false()
