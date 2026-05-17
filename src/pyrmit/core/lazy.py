"""``Lazy[T]`` -- a sentinel for deferred, context-resolved values.

Adapters frequently want to accept either a *concrete* dependency or a
*resolver* that produces it lazily (e.g. so a Strawberry/FastAPI app can
read the dependency off the per-request context rather than capturing
it at module import time). Disambiguating "is this a value or a
callable that returns the value?" via ``callable()`` is fragile -- many
real values (engines, ORM sessions, dataclass instances with
``__call__``) are themselves callable.

``Lazy[T]`` is the explicit sentinel that resolves this ambiguity at
the call site:

    policy_guard(engine=engine, ...)                          # concrete
    policy_guard(engine=Lazy(lambda info: info.context.engine), ...)  # deferred

Adapters check ``isinstance(value, Lazy)`` and call
:meth:`Lazy.aresolve` with whatever per-call context they have. The
resolver may be sync or async (or return an awaitable); ``aresolve``
normalizes both forms.

Type note: the resolver's parameter list is intentionally open
(``Callable[..., ...]``) so the same sentinel can carry resolvers
across adapters whose per-call contexts have framework-specific types
(Strawberry ``Info``, FastAPI ``Request``, ...). This is the only
explicit ``Any`` surface in :mod:`pyrmit.core`; it bridges to the
framework-boundary ``Any`` surfaces inside ``pyrmit.adapters.*``. The
narrowly-scoped mypy override that permits ``Any`` in this single
module is configured in ``pyproject.toml``.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Lazy[T]:
    """Wraps a resolver so adapters know to defer evaluation.

    The wrapped resolver receives whatever per-call context the adapter
    provides (Strawberry ``Info``, FastAPI ``Request``, etc.) and
    returns either the concrete ``T`` synchronously or an awaitable
    that resolves to ``T``.

    Attributes:
        fn: The resolver function. Receives the adapter-supplied
            context as a single positional argument and returns ``T``
            or ``Awaitable[T]``.
    """

    fn: Callable[[Any], T | Awaitable[T]]

    async def aresolve(self, ctx: object) -> T:
        """Resolve the wrapped value, awaiting if the resolver is async.

        Args:
            ctx: The per-call context to pass to the resolver. Typed
                as ``object`` here because :class:`Lazy` does not know
                the framework-specific shape of context the calling
                adapter will hand in.

        Returns:
            The resolved ``T``.
        """
        result = self.fn(ctx)
        if inspect.isawaitable(result):
            awaited: T = await result
            return awaited
        # Non-awaitable branch of the union returns T directly.
        return result
