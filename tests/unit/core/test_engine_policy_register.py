"""Unit tests for the @engine.policy decorator."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, DenialSurface
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import DuplicatePolicyError


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestPolicyDecorator:
    def test_register_one_policy(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        bindings = engine.registered_bindings()
        assert_that(bindings).is_length(1)
        assert_that(bindings[0].action).is_equal_to(_Action.READ)
        assert_that(bindings[0].subject_type).is_equal_to(_Subject)
        assert_that(bindings[0].denial_surface).is_equal_to(DenialSurface.FORBIDDEN)

    def test_register_with_explicit_denial_surface(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(
            action=_Action.READ,
            subject_type=_Subject,
            denial_surface=DenialSurface.NULL,
        )
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        assert_that(engine.registered_bindings()[0].denial_surface).is_equal_to(DenialSurface.NULL)

    def test_duplicate_registration_raises(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _first(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        try:

            @engine.policy(action=_Action.READ, subject_type=_Subject)
            def _dup(_p: object, _s: _Subject) -> Decision:
                return ALLOW

        except DuplicatePolicyError as err:
            assert_that(err.action).is_equal_to(_Action.READ.value)
            assert_that(err.subject_type).is_equal_to(_Subject.__name__)
            return
        assert_that(False).described_as("expected DuplicatePolicyError").is_true()
