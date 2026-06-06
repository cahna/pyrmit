"""Tests for ``visibility_scope`` decorator metadata + signature preservation."""

from __future__ import annotations

import inspect

from assertpy import assert_that
from sqlalchemy import ColumnElement, Integer, String
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from pyrmit.adapters.sqlalchemy import visibility_scope


class _Base(DeclarativeBase):
    pass


class _Match(_Base):
    __tablename__ = "matches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)


@visibility_scope(model=_Match)
def _match_visibility(principal_name: str) -> ColumnElement[bool]:
    """Visibility predicate for the Match model.

    Args:
        principal_name: The caller's display name.
    """
    return _Match.name == principal_name


class TestVisibilityScopeDecorator:
    def test_preserves_name(self) -> None:
        assert_that(_match_visibility.__name__).is_equal_to("_match_visibility")

    def test_preserves_docstring(self) -> None:
        assert_that(_match_visibility.__doc__).contains("Visibility predicate")

    def test_preserves_signature(self) -> None:
        sig = inspect.signature(_match_visibility)
        assert_that(list(sig.parameters)).is_equal_to(["principal_name"])

    def test_attaches_model_metadata(self) -> None:
        assert_that(
            _match_visibility.__pyrmit_scope_model__  # type: ignore[attr-defined]  # noqa: SLF001
        ).is_equal_to(_Match)

    def test_callable_returns_column_element(self) -> None:
        predicate = _match_visibility("alice")
        # SQLAlchemy ColumnElement -- it MUST be usable in .where()
        assert_that(hasattr(predicate, "compile")).is_true()
