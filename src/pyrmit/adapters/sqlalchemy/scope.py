"""``visibility_scope`` decorator + scope-presence assertion.

The decorator is metadata-only -- the application calls the wrapped
function explicitly and composes the result via ``query.where(...)``.
The library does NOT generate SQL from policy functions; callers retain
full control over the query they build.
"""

from __future__ import annotations

import functools
from collections.abc import Callable
from typing import Any

from sqlalchemy import ColumnElement
from sqlalchemy.sql import Select

_SCOPE_MODEL_ATTR = "__pyrmit_scope_model__"


def visibility_scope(
    *,
    model: type[Any],
) -> Callable[[Callable[..., ColumnElement[bool]]], Callable[..., ColumnElement[bool]]]:
    """Mark a function as the visibility predicate for ``model``.

    The decorator does NOT change runtime behavior; it attaches a small
    metadata attribute that ``verify_scope_applied`` inspects to verify
    the scope is genuinely applied to the query.

    Args:
        model: The SQLAlchemy model the predicate governs.
    """

    def _decorator(
        fn: Callable[..., ColumnElement[bool]],
    ) -> Callable[..., ColumnElement[bool]]:
        @functools.wraps(fn)
        def _wrapper(*args: Any, **kwargs: Any) -> ColumnElement[bool]:
            return fn(*args, **kwargs)

        # Attach metadata for assertion-helper inspection.
        setattr(_wrapper, _SCOPE_MODEL_ATTR, model)
        return _wrapper

    return _decorator


def verify_scope_applied(
    query: Select[Any],
    *,
    expected_scope: Callable[..., ColumnElement[bool]] | ColumnElement[bool],
) -> None:
    """Verify the predicate produced by ``expected_scope`` is in ``query``.

    .. warning::

        This helper is a **tripwire, not a proof**. The structural and
        text comparisons can be defeated by subqueries, CTEs, UNION
        ALL, or any composition that places the scope predicate on an
        inner query whose outer projection re-exposes filtered rows.
        Use it as a regression guard in unit tests, not as a substitute
        for code review of row-level visibility.

    Three substantive checks:

    1. **Where-clause exists.** Without a where-clause the scope cannot
       have been applied.
    2. **Model-FROM consistency.** The model the scope is decorated for
       (``visibility_scope(model=...)``) MUST appear in the query's
       FROM targets. Otherwise the helper is being called against a
       query that selects from a different model than the scope governs.
    3. **Predicate identity.** The scope's compiled SQL text MUST be a
       substring of the query's compiled where-clause text. Two calls
       to the same decorated function produce the same SQL string, so
       this is a tight check -- a query with an unrelated
       ``query.where(SomethingElse.foo == 1)`` will fail this check.

    Args:
        query: The SQLAlchemy ``Select`` statement to inspect.
        expected_scope: Either the visibility-scope-decorated function
            the query should have consulted (preferred; the helper
            calls it with no arguments to obtain the predicate), or
            the predicate value directly (e.g. ``my_scope(actor)``).

    Raises:
        AssertionError: If any of the three substantive checks fails;
            the message names which check failed.
    """
    # Resolve the predicate value and the scope-model metadata.
    if isinstance(expected_scope, ColumnElement):
        scope_predicate: ColumnElement[bool] = expected_scope
        scope_model = None
    else:
        scope_model = getattr(expected_scope, _SCOPE_MODEL_ATTR, None)
        try:
            scope_predicate = expected_scope()
        except TypeError as err:
            msg = (
                f"expected_scope requires arguments; wrap it in a zero-arg "
                f"lambda for verify_scope_applied "
                f"(e.g. lambda: scope(actor)) or pass the predicate value "
                f"directly. Underlying TypeError: {err}"
            )
            raise AssertionError(msg) from err

    # Check #1: where-clause present.
    where_clauses = query.whereclause
    if where_clauses is None:
        msg = f"query has no where-clause; visibility scope for model {scope_model!r} was not applied"
        raise AssertionError(msg)

    # Check #2: scope's model is in the query's FROM targets.
    if scope_model is not None:
        scope_table = getattr(scope_model, "__table__", scope_model)
        from_targets = query.get_final_froms()
        in_froms = any(
            target is scope_table or getattr(target, "entity_namespace", None) is scope_model for target in from_targets
        )
        if not in_froms:
            msg = (
                f"query's FROM clause does not target model {scope_model!r}; "
                f"expected_scope is registered against a different model "
                f"than the one this query selects from"
            )
            raise AssertionError(msg)

    # Check #3: scope's predicate text is a substring of where-clause text.
    # We deliberately do NOT compile with literal_binds=True -- materialising
    # bind values into the assertion message would leak user-supplied data
    # (potentially PII) into logs and tracebacks on failure.
    scope_sql = str(scope_predicate.compile())
    where_sql = str(where_clauses.compile())
    if scope_sql not in where_sql:
        msg = (
            f"expected scope predicate not present in where-clause for "
            f"model {scope_model!r}.\n"
            f"  Expected (substring): {scope_sql}\n"
            f"  Got (where-clause):   {where_sql}"
        )
        raise AssertionError(msg)
