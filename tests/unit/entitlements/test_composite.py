"""Tests for CompositeEntitlementProvider."""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.composite import CompositeEntitlementProvider
from pyrmit.entitlements.static import StaticEntitlementProvider


class _Feature(StrEnum):
    A = "a"
    B = "b"
    C = "c"


class _RaisingProvider:
    """An entitlement provider that always raises."""

    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """Always raise to exercise the failure-tolerance branch."""
        del lookup  # unused
        raise RuntimeError("provider exploded")


class TestCompositeEntitlementProvider:
    def test_union_of_inner_provider_results(self) -> None:
        p1 = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.A, _Feature.B})})
        p2 = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.B, _Feature.C})})
        composite = CompositeEntitlementProvider[str, _Feature](providers=[p1, p2])
        result = asyncio.run(composite.entitlements_for("alice"))
        assert_that(set(result)).is_equal_to({_Feature.A, _Feature.B, _Feature.C})

    def test_raising_inner_contributes_empty_and_logs_warning(
        self,
        caplog: object,
    ) -> None:
        # narrow: caplog is the pytest fixture (LogCaptureFixture).
        from _pytest.logging import LogCaptureFixture

        assert isinstance(caplog, LogCaptureFixture)  # narrow: type-narrow caplog

        good = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.A})})
        bad = _RaisingProvider()
        composite = CompositeEntitlementProvider[str, _Feature](providers=[good, bad])

        with caplog.at_level(logging.WARNING, logger="pyrmit.entitlements.composite"):
            result = asyncio.run(composite.entitlements_for("alice"))

        assert_that(set(result)).is_equal_to({_Feature.A})
        assert_that(caplog.records).is_not_empty()
        assert_that(caplog.records[0].levelname).is_equal_to("WARNING")

    def test_empty_provider_list_yields_empty(self) -> None:
        composite = CompositeEntitlementProvider[str, _Feature](providers=[])
        result = asyncio.run(composite.entitlements_for("alice"))
        assert_that(len(result)).is_equal_to(0)

    def test_repeated_invocation_is_idempotent(self) -> None:
        p1 = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.A})})
        p2 = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.B})})
        composite = CompositeEntitlementProvider[str, _Feature](providers=[p1, p2])
        first = asyncio.run(composite.entitlements_for("alice"))
        second = asyncio.run(composite.entitlements_for("alice"))
        assert_that(first).is_equal_to(second)

    def test_cancelled_error_in_inner_provider_propagates(self) -> None:
        """CancelledError MUST NOT be swallowed as an empty entitlement set.

        Regression: ``asyncio.gather(return_exceptions=True)`` includes
        ``CancelledError`` in the results, and the prior
        ``isinstance(result, BaseException)`` branch silently converted
        it into "this provider contributed nothing." That corrupted
        cancellation semantics for the caller -- a cancelled inner
        coroutine would return the OTHER provider's results instead of
        propagating cancellation.
        """

        class _CancellingProvider:
            async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
                del lookup
                raise asyncio.CancelledError

        good = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.A})})
        composite = CompositeEntitlementProvider[str, _Feature](providers=[good, _CancellingProvider()])

        raised = False
        try:
            asyncio.run(composite.entitlements_for("alice"))
        except asyncio.CancelledError:
            raised = True
        assert_that(raised).is_true()
