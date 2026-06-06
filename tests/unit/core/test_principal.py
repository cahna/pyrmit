"""Unit tests for `pyrmit.core.principal`."""

from __future__ import annotations

from dataclasses import FrozenInstanceError, dataclass
from uuid import UUID

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


@dataclass(frozen=True)
class _Actor:
    user_id: UUID
    is_admin: bool


class TestPrincipal:
    def test_construct_with_actor_and_entitlements(self) -> None:
        actor = _Actor(user_id=UUID(int=1), is_admin=False)
        p: Principal[_Actor, str] = Principal(
            actor=actor,
            entitlements=Entitlements.empty(),
        )
        assert_that(p.actor).is_equal_to(actor)
        assert_that(len(p.entitlements)).is_equal_to(0)
        assert_that(p.request_id).is_none()

    def test_request_id_passes_through(self) -> None:
        actor = _Actor(user_id=UUID(int=1), is_admin=True)
        p: Principal[_Actor, str] = Principal(
            actor=actor,
            entitlements=Entitlements.empty(),
            request_id="trace-abc",
        )
        assert_that(p.request_id).is_equal_to("trace-abc")

    def test_principal_is_frozen(self) -> None:
        actor = _Actor(user_id=UUID(int=1), is_admin=False)
        p: Principal[_Actor, str] = Principal(
            actor=actor,
            entitlements=Entitlements.empty(),
        )
        # narrow: confirming frozen-dataclass behavior raises on set
        try:
            p.actor = _Actor(user_id=UUID(int=2), is_admin=True)  # type: ignore[misc]
        except FrozenInstanceError:
            return
        assert_that(False).described_as("expected FrozenInstanceError").is_true()

    def test_structural_equality(self) -> None:
        actor = _Actor(user_id=UUID(int=1), is_admin=False)
        a: Principal[_Actor, str] = Principal(actor=actor, entitlements=Entitlements.empty())
        b: Principal[_Actor, str] = Principal(actor=actor, entitlements=Entitlements.empty())
        assert_that(a).is_equal_to(b)
