"""Decision.detail is defensively copied so callers cannot mutate a frozen value."""

from __future__ import annotations

from types import MappingProxyType
from typing import cast

import pytest
from assertpy import assert_that

from pyrmit.core.decision import Decision, DetailValue, deny


class TestDecisionDetailImmutability:
    def test_direct_constructor_defensively_copies_mutable_dict(self) -> None:
        original: dict[str, DetailValue] = {"k": "v"}
        d = Decision(allowed=False, reason="x", detail=original)
        original["k"] = "mutated"
        original["new"] = "added"
        assert_that(dict(d.detail)).is_equal_to({"k": "v"})

    def test_detail_is_a_mappingproxytype_after_construction(self) -> None:
        d = Decision(allowed=False, reason="x", detail={"k": "v"})
        assert_that(isinstance(d.detail, MappingProxyType)).is_true()

    def test_existing_mappingproxytype_is_not_rewrapped(self) -> None:
        # When the caller already supplies a MappingProxyType, skip the copy.
        proxy: MappingProxyType[str, DetailValue] = MappingProxyType({"k": "v"})
        d = Decision(allowed=False, reason="x", detail=proxy)
        assert_that(d.detail).is_same_as(proxy)

    def test_deny_helper_continues_to_produce_immutable_detail(self) -> None:
        d = deny("x", k="v")
        assert_that(isinstance(d.detail, MappingProxyType)).is_true()

    def test_int_and_bool_values_accepted(self) -> None:
        d = deny("x", count=5, ok=True, name="alice")
        assert_that(dict(d.detail)).is_equal_to({"count": 5, "ok": True, "name": "alice"})

    def test_non_primitive_value_rejected_at_construction(self) -> None:
        # Cast through Any to simulate a caller routing through an untyped
        # adapter boundary.
        with pytest.raises(TypeError) as exc_info:
            Decision(
                allowed=False,
                reason="x",
                detail=cast(dict[str, DetailValue], {"bad": [1, 2, 3]}),
            )
        assert_that(str(exc_info.value)).contains("str | int | bool")
