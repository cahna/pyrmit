"""Tests for verify_scope_applied."""

from __future__ import annotations

from assertpy import assert_that
from sqlalchemy import Boolean, ColumnElement, Integer, String, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pyrmit.adapters.sqlalchemy import (
    verify_scope_applied,
    visibility_scope,
)


class _Base(DeclarativeBase):
    pass


class _Article(_Base):
    __tablename__ = "articles_ord"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String)
    is_published: Mapped[bool] = mapped_column(Boolean)


@visibility_scope(model=_Article)
def _scope() -> ColumnElement[bool]:
    return _Article.is_published.is_(True)


class TestVerifyScopeApplied:
    def test_passes_when_scope_applied(self) -> None:
        query = select(_Article).where(_scope()).limit(10).offset(0)
        # MUST NOT raise.
        verify_scope_applied(
            query,
            expected_scope=_scope,
        )

    def test_raises_when_query_has_no_where_clause(self) -> None:
        query = select(_Article).limit(10).offset(0)
        try:
            verify_scope_applied(
                query,
                expected_scope=_scope,
            )
        except AssertionError as err:
            assert_that(str(err)).contains("scope")
            return
        assert_that(False).described_as("expected AssertionError").is_true()

    def test_raises_when_unrelated_where_clause_passes_off_as_scope(
        self,
    ) -> None:
        """A query that has SOME where-clause but NOT the scope's
        predicate MUST fail. This catches the original review #3 weakness:
        the prior helper only checked "any where-clause exists" and would
        pass for ``query.where(Unrelated.foo == 1)`` even when the scope
        was not applied.
        """
        # Build a query with an unrelated where-clause (no use of _scope).
        query = select(_Article).where(_Article.owner == "alice")
        try:
            verify_scope_applied(
                query,
                expected_scope=_scope,
            )
        except AssertionError as err:
            assert_that(str(err)).contains("not present")
            return
        assert_that(False).described_as("expected AssertionError on unrelated where-clause").is_true()

    def test_accepts_predicate_directly_instead_of_callable(self) -> None:
        """Users may pass the predicate value directly (skipping the
        zero-arg lambda dance) when the scope function takes arguments."""
        predicate = _scope()
        query = select(_Article).where(predicate)
        # MUST NOT raise.
        verify_scope_applied(query, expected_scope=predicate)

    def test_assertion_message_does_not_leak_bind_values(self) -> None:
        """Failure messages must NOT compile with literal_binds=True;
        materialising bind values into AssertionError messages would
        leak user-supplied data into logs and tracebacks."""
        secret_owner = "secret-pii-owner-12345"
        query = select(_Article).where(_Article.owner == secret_owner)
        try:
            verify_scope_applied(query, expected_scope=_scope)
        except AssertionError as err:
            assert_that(str(err)).does_not_contain(secret_owner)
            return
        assert_that(False).described_as("expected AssertionError").is_true()
