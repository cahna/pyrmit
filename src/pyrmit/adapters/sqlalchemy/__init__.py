"""SQLAlchemy adapter: visibility scope + scope-presence assertion."""

from __future__ import annotations

from pyrmit.adapters.sqlalchemy.scope import (
    verify_scope_applied,
    visibility_scope,
)

__all__ = [
    "verify_scope_applied",
    "visibility_scope",
]
