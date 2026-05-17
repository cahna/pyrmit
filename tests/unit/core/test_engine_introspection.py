"""Unit tests for engine.binding_for and engine.registered_bindings."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, DenialSurface
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestIntrospection:
    def test_binding_for_returns_binding_when_registered(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(
            action=_Action.READ,
            subject_type=_Subject,
            denial_surface=DenialSurface.NULL,
        )
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        binding = engine.binding_for(
            action=_Action.READ,
            subject_type=_Subject,
        )
        assert_that(binding).is_not_none()
        assert binding is not None  # narrow: type-narrow before attribute access
        assert_that(binding.denial_surface).is_equal_to(DenialSurface.NULL)
        assert_that(binding.action).is_equal_to(_Action.READ)

    def test_binding_for_returns_none_when_missing(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()
        binding = engine.binding_for(
            action=_Action.WRITE,
            subject_type=_Subject,
        )
        assert_that(binding).is_none()

    def test_registered_bindings_returns_all_in_registration_order(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_Subject)
        def _r(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.WRITE, subject_type=_Subject)
        def _w(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        bindings = engine.registered_bindings()
        assert_that(bindings).is_length(2)
        assert_that(bindings[0].action).is_equal_to(_Action.READ)
        assert_that(bindings[1].action).is_equal_to(_Action.WRITE)
