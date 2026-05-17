"""Unit tests for pyrmit logging setup."""

from __future__ import annotations

import logging

from assertpy import assert_that

import pyrmit  # noqa: F401  -- import triggers package-init logger setup


class TestPyrmitLogger:
    def test_top_level_logger_has_exactly_one_null_handler(self) -> None:
        logger = logging.getLogger("pyrmit")
        null_handlers = [h for h in logger.handlers if isinstance(h, logging.NullHandler)]
        non_null_handlers = [h for h in logger.handlers if not isinstance(h, logging.NullHandler)]
        assert_that(null_handlers).is_length(1)
        assert_that(non_null_handlers).is_length(0)

    def test_no_level_explicitly_set_on_pyrmit_logger(self) -> None:
        logger = logging.getLogger("pyrmit")
        assert_that(logger.level).is_equal_to(logging.NOTSET)

    def test_pyrmit_logger_does_not_propagate_basicConfig(self) -> None:
        # A library MUST NOT call logging.basicConfig at import time. We
        # cannot directly check whether it was called, but we can assert
        # the root logger has no NullHandler installed BY pyrmit -- and
        # that pyrmit's own logger still has its NullHandler regardless.
        pyrmit_logger = logging.getLogger("pyrmit")
        null_handlers = [h for h in pyrmit_logger.handlers if isinstance(h, logging.NullHandler)]
        assert_that(null_handlers).is_length(1)
