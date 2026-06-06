"""Tests for LoggingAuditStore."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime

from assertpy import assert_that

from pyrmit.audit.logging import LoggingAuditStore
from pyrmit.core.audit import AuditEntry, AuditOutcome


def _entry() -> AuditEntry:
    return AuditEntry(
        id="id-0001",
        timestamp=datetime(2026, 5, 17, tzinfo=UTC),
        outcome=AuditOutcome.DENIED,
        action="read",
        subject_type="Article",
        subject_id="a-1",
        actor_id="u-1",
        reason="article_unpublished",
    )


class TestLoggingAuditStore:
    def test_logs_at_info_level(self, caplog: object) -> None:
        from _pytest.logging import LogCaptureFixture

        assert isinstance(caplog, LogCaptureFixture)  # narrow: pytest fixture

        store = LoggingAuditStore(logger_name="pyrmit.audit.test")
        with caplog.at_level(logging.INFO, logger="pyrmit.audit.test"):
            asyncio.run(store.write(_entry()))

        assert_that(caplog.records).is_not_empty()
        record = caplog.records[0]
        assert_that(record.levelname).is_equal_to("INFO")
        assert_that(record.name).is_equal_to("pyrmit.audit.test")

    def test_logging_store_does_not_install_handlers(self) -> None:
        logger = logging.getLogger("pyrmit.audit.handler_test")
        before = list(logger.handlers)
        store = LoggingAuditStore(logger_name="pyrmit.audit.handler_test")
        asyncio.run(store.write(_entry()))
        after = list(logger.handlers)
        # LoggingAuditStore MUST be a good library citizen: it MUST NOT
        # install handlers on the host application's logging stack.
        assert_that(after).is_equal_to(before)
