"""Unit tests for engine.replace_policy."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestReplacePolicy:
    def test_replace_overrides_existing_binding(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _first(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        @engine.replace_policy(action=_Action.READ, subject_type=_Subject)
        def _second(_p: object, _s: _Subject) -> Decision:
            return deny("override")

        # The new policy is now active.
        bindings = engine.registered_bindings()
        assert_that(bindings).is_length(1)
        d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_Subject(id=1),
        )
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("override")

    def test_replace_with_no_prior_binding_succeeds(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.replace_policy(
            action=_Action.READ,
            subject_type=_Subject,
            denial_surface=DenialSurface.NULL,
        )
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        bindings = engine.registered_bindings()
        assert_that(bindings).is_length(1)
        assert_that(bindings[0].denial_surface).is_equal_to(DenialSurface.NULL)
