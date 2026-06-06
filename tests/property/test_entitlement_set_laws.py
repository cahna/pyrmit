"""Property tests for Entitlements set algebra."""

from __future__ import annotations

from enum import StrEnum

from assertpy import assert_that
from hypothesis import given
from hypothesis import strategies as st

from pyrmit.core.entitlements import Entitlements


class _Feature(StrEnum):
    A = "a"
    B = "b"
    C = "c"
    D = "d"


_feature_st: st.SearchStrategy[_Feature] = st.sampled_from(list(_Feature))


def _ent(items: frozenset[_Feature]) -> Entitlements[_Feature]:
    """Construct an Entitlements set from a Hypothesis-generated frozenset."""
    return Entitlements[_Feature](items)


class TestEntitlementsLaws:
    @given(items=st.frozensets(_feature_st, max_size=4))
    def test_equality_is_reflexive(self, items: frozenset[_Feature]) -> None:
        e = _ent(items)
        assert_that(e).is_equal_to(_ent(items))

    @given(items=st.frozensets(_feature_st, max_size=4))
    def test_hash_matches_equality(self, items: frozenset[_Feature]) -> None:
        a = _ent(items)
        b = _ent(items)
        assert_that(hash(a)).is_equal_to(hash(b))

    @given(items=st.frozensets(_feature_st, max_size=4))
    def test_iter_yields_set_members(
        self,
        items: frozenset[_Feature],
    ) -> None:
        e = _ent(items)
        assert_that(set(iter(e))).is_equal_to(set(items))

    @given(items=st.frozensets(_feature_st, max_size=4))
    def test_has_matches_membership(
        self,
        items: frozenset[_Feature],
    ) -> None:
        e = _ent(items)
        for feature in _Feature:
            expected = feature in items
            assert_that(e.has(feature)).described_as(f"has({feature.value})").is_equal_to(expected)

    @given(items=st.frozensets(_feature_st, max_size=4))
    def test_has_all_vacuous_truth(
        self,
        items: frozenset[_Feature],
    ) -> None:
        e = _ent(items)
        assert_that(e.has_all()).is_true()

    @given(
        items=st.frozensets(_feature_st, max_size=4),
        probe=st.frozensets(_feature_st, max_size=4),
    )
    def test_has_all_iff_subset(
        self,
        items: frozenset[_Feature],
        probe: frozenset[_Feature],
    ) -> None:
        e = _ent(items)
        expected = probe.issubset(items)
        assert_that(e.has_all(*probe)).is_equal_to(expected)
