"""Unit tests for `pyrmit.core.decision`."""

from __future__ import annotations

from types import MappingProxyType

import pytest
from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny


class TestDecision:
    def test_allow_singleton_has_allowed_true_and_no_reason(self) -> None:
        assert_that(ALLOW.allowed).is_true()
        assert_that(ALLOW.reason).is_none()
        assert_that(dict(ALLOW.detail)).is_empty()

    def test_allow_is_a_decision_instance(self) -> None:
        assert_that(isinstance(ALLOW, Decision)).is_true()

    def test_deny_returns_decision_with_reason(self) -> None:
        d = deny("article_unpublished")
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("article_unpublished")
        assert_that(dict(d.detail)).is_empty()

    def test_deny_kwargs_become_detail_mapping(self) -> None:
        d = deny("missing_required_entitlement", required="advanced_search")
        assert_that(d.allowed).is_false()
        assert_that(d.reason).is_equal_to("missing_required_entitlement")
        assert_that(dict(d.detail)).is_equal_to({"required": "advanced_search"})

    def test_deny_detail_is_immutable(self) -> None:
        d = deny("not_owner", actor="u1")
        assert_that(isinstance(d.detail, MappingProxyType)).is_true()

    def test_decision_is_frozen_dataclass(self) -> None:
        from dataclasses import FrozenInstanceError

        # narrow: confirming attribute write actually raises
        try:
            ALLOW.reason = "x"  # type: ignore[misc]
        except FrozenInstanceError:
            return
        assert_that(False).described_as("expected FrozenInstanceError").is_true()

    def test_decision_structural_equality(self) -> None:
        a = deny("x", k="v")
        b = deny("x", k="v")
        assert_that(a).is_equal_to(b)

    def test_allow_with_reason_is_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            Decision(allowed=True, reason="why_is_this_here")
        assert_that(str(exc_info.value)).contains("reason=None")

    def test_deny_without_reason_is_rejected(self) -> None:
        with pytest.raises(ValueError) as exc_info:
            Decision(allowed=False)
        assert_that(str(exc_info.value)).contains("non-None reason")


class TestDenialSurface:
    def test_string_values_match_contract(self) -> None:
        assert_that(DenialSurface.FORBIDDEN.value).is_equal_to("forbidden")
        assert_that(DenialSurface.NULL.value).is_equal_to("null")
        assert_that(DenialSurface.NOT_FOUND.value).is_equal_to("not_found")

    def test_denial_surface_membership(self) -> None:
        members = {m.value for m in DenialSurface}
        assert_that(members).is_equal_to({"forbidden", "null", "not_found"})
