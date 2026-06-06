"""Unit tests for `pyrmit.core.errors`."""

from __future__ import annotations

from assertpy import assert_that

from pyrmit.core.errors import (
    ConfigurationError,
    DuplicatePolicyError,
    DuplicateResolverError,
)


class TestDuplicatePolicyError:
    def test_is_an_exception(self) -> None:
        err = DuplicatePolicyError(action="read", subject_type="Article")
        assert_that(isinstance(err, Exception)).is_true()
        assert_that(err.action).is_equal_to("read")
        assert_that(err.subject_type).is_equal_to("Article")

    def test_is_raisable(self) -> None:
        try:
            raise DuplicatePolicyError(action="read", subject_type="Article")
        except DuplicatePolicyError as caught:
            assert_that(caught.action).is_equal_to("read")
            return
        assert_that(False).described_as("expected raise to propagate").is_true()


class TestDuplicateResolverError:
    def test_is_an_exception(self) -> None:
        err = DuplicateResolverError(subject_type="Article")
        assert_that(isinstance(err, Exception)).is_true()
        assert_that(err.subject_type).is_equal_to("Article")


class TestConfigurationError:
    def test_is_an_exception(self) -> None:
        err = ConfigurationError(message="bad binding", binding="Article.READ")
        assert_that(isinstance(err, Exception)).is_true()

    def test_binding_is_optional(self) -> None:
        err = ConfigurationError(message="schema-level misconfig")
        assert_that(err.binding).is_none()
        assert_that(str(err)).contains("<unspecified>")

    def test_binding_rendered_in_str_when_present(self) -> None:
        err = ConfigurationError(message="oops", binding="Article.read")
        assert_that(str(err)).contains("Article.read")
        assert_that(str(err)).contains("oops")
