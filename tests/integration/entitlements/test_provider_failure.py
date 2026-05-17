"""Boundary semantics: a raising provider yields empty entitlements."""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from assertpy import assert_that

from pyrmit.core.entitlements import Entitlements
from pyrmit.entitlements.composite import CompositeEntitlementProvider
from pyrmit.entitlements.static import StaticEntitlementProvider


class _Feature(StrEnum):
    PAID = "paid"


class _RaisingProvider:
    async def entitlements_for(self, lookup: str) -> Entitlements[_Feature]:
        """Always raise to exercise the failure-tolerance branch."""
        del lookup
        raise RuntimeError("provider exploded")


class TestProviderFailureBoundary:
    def test_composite_treats_inner_failure_as_empty_set(
        self,
        caplog: object,
    ) -> None:
        from _pytest.logging import LogCaptureFixture

        assert isinstance(caplog, LogCaptureFixture)  # narrow: caplog fixture

        only_bad = CompositeEntitlementProvider[str, _Feature](providers=[_RaisingProvider()])
        with caplog.at_level(
            logging.WARNING,
            logger="pyrmit.entitlements.composite",
        ):
            result = asyncio.run(only_bad.entitlements_for("alice"))

        # The boundary swallows the raise and yields an empty set,
        # which causes entitlement-gated policies to deny -- the
        # fail-closed default.
        assert_that(len(result)).is_equal_to(0)
        assert_that(caplog.records).is_not_empty()

    def test_one_good_plus_one_bad_yields_good_only(
        self,
        caplog: object,
    ) -> None:
        from _pytest.logging import LogCaptureFixture

        assert isinstance(caplog, LogCaptureFixture)  # narrow: caplog fixture

        good = StaticEntitlementProvider[str, _Feature](mapping={"alice": frozenset({_Feature.PAID})})
        composite = CompositeEntitlementProvider[str, _Feature](providers=[good, _RaisingProvider()])
        with caplog.at_level(
            logging.WARNING,
            logger="pyrmit.entitlements.composite",
        ):
            result = asyncio.run(composite.entitlements_for("alice"))

        assert_that(set(result)).is_equal_to({_Feature.PAID})
