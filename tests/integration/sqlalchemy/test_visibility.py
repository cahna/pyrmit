"""SQLAlchemy visibility-scope integration against SQLite in-memory."""

from __future__ import annotations

from assertpy import assert_that
from sqlalchemy import (
    Boolean,
    ColumnElement,
    Integer,
    String,
    create_engine,
    select,
    true,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from pyrmit.adapters.sqlalchemy import visibility_scope


class _Base(DeclarativeBase):
    pass


class _Article(_Base):
    __tablename__ = "articles"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner: Mapped[str] = mapped_column(String)
    is_published: Mapped[bool] = mapped_column(Boolean)


@visibility_scope(model=_Article)
def _article_visibility(
    actor_name: str,
    *,
    is_admin: bool,
) -> ColumnElement[bool]:
    if is_admin:
        return true()
    return _Article.is_published.is_(True) | (_Article.owner == actor_name)


class TestVisibilityScopeIntegration:
    def test_admin_sees_all_rows(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        _Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all([
                _Article(id=1, owner="alice", is_published=True),
                _Article(id=2, owner="alice", is_published=False),
                _Article(id=3, owner="bob", is_published=False),
            ])
            session.commit()

            query = select(_Article).where(_article_visibility("admin-noname", is_admin=True))
            rows = session.execute(query).scalars().all()
            assert_that([r.id for r in rows]).is_equal_to([1, 2, 3])

    def test_user_sees_published_or_own(self) -> None:
        engine = create_engine("sqlite:///:memory:")
        _Base.metadata.create_all(engine)
        with Session(engine) as session:
            session.add_all([
                _Article(id=1, owner="alice", is_published=True),
                _Article(id=2, owner="alice", is_published=False),
                _Article(id=3, owner="bob", is_published=False),
            ])
            session.commit()

            query = select(_Article).where(_article_visibility("alice", is_admin=False))
            rows = session.execute(query).scalars().all()
            assert_that(sorted(r.id for r in rows)).is_equal_to([1, 2])
