"""Unit tests for `pyrmit.core.binding`."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.binding import PolicyBinding
from pyrmit.core.decision import ALLOW, Decision, DenialSurface
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


@dataclass(frozen=True)
class _Actor:
    name: str


def _policy(_p: Principal[_Actor, str], _s: _Subject) -> Decision:
    return ALLOW


class TestPolicyBinding:
    def test_construct_with_required_fields(self) -> None:
        b: PolicyBinding[Principal[_Actor, str], _Action, _Subject] = PolicyBinding(
            action=_Action.READ,
            subject_type=_Subject,
            policy=_policy,
            denial_surface=DenialSurface.FORBIDDEN,
        )
        assert_that(b.action).is_equal_to(_Action.READ)
        assert_that(b.subject_type).is_equal_to(_Subject)
        assert_that(b.policy).is_equal_to(_policy)
        assert_that(b.denial_surface).is_equal_to(DenialSurface.FORBIDDEN)

    def test_binding_is_frozen(self) -> None:
        from dataclasses import FrozenInstanceError

        b: PolicyBinding[Principal[_Actor, str], _Action, _Subject] = PolicyBinding(
            action=_Action.READ,
            subject_type=_Subject,
            policy=_policy,
            denial_surface=DenialSurface.NULL,
        )
        # narrow: confirming attribute write raises
        try:
            b.action = _Action.READ  # type: ignore[misc]
        except FrozenInstanceError:
            return
        assert_that(False).described_as("expected FrozenInstanceError").is_true()

    def test_binding_calls_policy(self) -> None:
        actor = _Actor(name="alice")
        principal: Principal[_Actor, str] = Principal(actor=actor, entitlements=Entitlements.empty())
        subject = _Subject(id=42)
        b: PolicyBinding[Principal[_Actor, str], _Action, _Subject] = PolicyBinding(
            action=_Action.READ,
            subject_type=_Subject,
            policy=_policy,
            denial_surface=DenialSurface.FORBIDDEN,
        )
        decision = b.policy(principal, subject)
        assert_that(decision.allowed).is_true()
