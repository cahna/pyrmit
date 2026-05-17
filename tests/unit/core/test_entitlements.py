"""Unit tests for `pyrmit.core.entitlements`."""

from __future__ import annotations

from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements


class Feature(StrEnum):
    BASIC = "basic"
    ADVANCED = "advanced"
    PRO = "pro"


class TestEntitlements:
    def test_empty_classmethod_returns_empty_set(self) -> None:
        e: Entitlements[Feature] = Entitlements.empty()
        assert_that(len(e)).is_equal_to(0)
        assert_that(list(e)).is_empty()

    def test_empty_is_cached_or_equal(self) -> None:
        # Either the classmethod returns the same singleton each call, or two
        # empties compare equal structurally; both are acceptable.
        a: Entitlements[Feature] = Entitlements.empty()
        b: Entitlements[Feature] = Entitlements.empty()
        assert_that(a).is_equal_to(b)

    def test_has_returns_true_for_present(self) -> None:
        e = Entitlements(frozenset({Feature.BASIC, Feature.ADVANCED}))
        assert_that(e.has(Feature.BASIC)).is_true()
        assert_that(e.has(Feature.PRO)).is_false()

    def test_contains_operator(self) -> None:
        e = Entitlements(frozenset({Feature.BASIC}))
        assert_that(Feature.BASIC in e).is_true()
        assert_that(Feature.PRO in e).is_false()

    def test_has_any(self) -> None:
        e = Entitlements(frozenset({Feature.BASIC}))
        assert_that(e.has_any(Feature.BASIC, Feature.PRO)).is_true()
        assert_that(e.has_any(Feature.ADVANCED, Feature.PRO)).is_false()

    def test_has_all(self) -> None:
        e = Entitlements(frozenset({Feature.BASIC, Feature.ADVANCED}))
        assert_that(e.has_all(Feature.BASIC, Feature.ADVANCED)).is_true()
        assert_that(e.has_all(Feature.BASIC, Feature.PRO)).is_false()

    def test_has_all_vacuous_truth(self) -> None:
        e: Entitlements[Feature] = Entitlements.empty()
        assert_that(e.has_all()).is_true()

    def test_iter_yields_all_members(self) -> None:
        items = {Feature.BASIC, Feature.ADVANCED}
        e = Entitlements(frozenset(items))
        assert_that(set(iter(e))).is_equal_to(items)

    def test_len_matches_set_size(self) -> None:
        e = Entitlements(frozenset({Feature.BASIC, Feature.ADVANCED}))
        assert_that(len(e)).is_equal_to(2)

    def test_structural_equality(self) -> None:
        a = Entitlements(frozenset({Feature.BASIC}))
        b = Entitlements(frozenset({Feature.BASIC}))
        assert_that(a).is_equal_to(b)
        assert_that(hash(a)).is_equal_to(hash(b))
