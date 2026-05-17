"""Runnable SQLAlchemy example: ``visibility_scope`` + ``verify_scope_applied``.

Run::

    uv run python examples/sqlalchemy/example.py

Demonstrates per-actor row-level visibility:

* The ``Article`` model stores ``owner_id`` and ``is_published``.
* ``article_visibility(actor)`` returns the visibility predicate for a
  given caller (published OR owned-by-actor; admins see all).
* A paginated listing query applies the predicate before LIMIT/OFFSET.
* ``verify_scope_applied`` confirms the predicate is genuinely present
  on the compiled query -- a tripwire-style regression guard.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Boolean, ColumnElement, Integer, String, create_engine, or_, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pyrmit.adapters.sqlalchemy import verify_scope_applied, visibility_scope


@dataclass(frozen=True)
class Actor:
    user_id: int
    is_admin: bool


class Base(DeclarativeBase):
    pass


class Article(Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(Integer)
    title: Mapped[str] = mapped_column(String)
    is_published: Mapped[bool] = mapped_column(Boolean)


@visibility_scope(model=Article)
def article_visibility(actor: Actor) -> ColumnElement[bool]:
    """Articles the given actor may see.

    The decorator carries the model metadata that
    ``verify_scope_applied`` inspects; the function body is plain
    SQLAlchemy.
    """
    if actor.is_admin:
        return Article.id.is_not(None)  # always-true predicate
    return or_(
        Article.is_published.is_(True),
        Article.owner_id == actor.user_id,
    )


def list_visible_articles(
    session: Session,
    *,
    actor: Actor,
    page: int,
    page_size: int,
) -> list[Article]:
    """Paginated listing with the visibility predicate applied first."""
    scope = article_visibility(actor)
    query = select(Article).where(scope).order_by(Article.id).limit(page_size).offset(page * page_size)
    # Tripwire: in tests we'd call verify_scope_applied(query, ...). Here
    # we demonstrate the inline call for documentation purposes.
    verify_scope_applied(query, expected_scope=scope)
    return list(session.scalars(query).all())


def _seed(session: Session) -> None:
    session.add_all([
        Article(id=1, owner_id=42, title="Hello, world", is_published=True),
        Article(id=2, owner_id=42, title="Draft post", is_published=False),
        Article(id=3, owner_id=99, title="Strangers draft", is_published=False),
        Article(id=4, owner_id=99, title="Strangers public", is_published=True),
    ])
    session.commit()


def main() -> None:
    """Build an in-memory SQLite DB and demonstrate the three-actor pattern."""
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)

    with Session(engine) as session:
        _seed(session)

        for label, actor in (
            ("admin", Actor(user_id=1, is_admin=True)),
            ("owner", Actor(user_id=42, is_admin=False)),
            ("stranger", Actor(user_id=99, is_admin=False)),
        ):
            visible = list_visible_articles(session, actor=actor, page=0, page_size=10)
            titles = [a.title for a in visible]
            print(f"[{label}] visible_titles={titles!r}")


if __name__ == "__main__":
    main()
