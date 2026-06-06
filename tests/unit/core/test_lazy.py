"""Unit tests for ``pyrmit.core.lazy.Lazy``.

The ``Lazy[T]`` sentinel wraps a resolver function so that adapter call
sites can pass *either* a concrete value or a deferred resolver without
the adapter having to disambiguate by ``callable()`` (which is brittle
in the presence of callable instances). Adapters look at
``isinstance(value, Lazy)`` and call :meth:`Lazy.resolve` (or
:meth:`Lazy.aresolve`) when they have whatever per-call context the
resolver needs.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable
from dataclasses import FrozenInstanceError

from assertpy import assert_that

from pyrmit.core.lazy import Lazy


class TestLazyConstruction:
    def test_lazy_is_frozen(self) -> None:
        lazy: Lazy[object] = Lazy(lambda ctx: ctx)
        try:
            lazy.fn = lambda ctx: ctx  # type: ignore[misc]
        except FrozenInstanceError:
            return
        assert_that(False).described_as("expected FrozenInstanceError").is_true()

    def test_lazy_stores_callable_unchanged(self) -> None:
        def resolver(ctx: object) -> str:
            del ctx
            return "engine"

        lazy: Lazy[str] = Lazy(resolver)
        assert_that(lazy.fn).is_equal_to(resolver)


class TestLazyResolveSync:
    def test_resolve_calls_sync_function_with_context(self) -> None:
        captured: list[object] = []

        def resolver(ctx: object) -> str:
            captured.append(ctx)
            return "value"

        lazy: Lazy[str] = Lazy(resolver)
        result = asyncio.run(lazy.aresolve("the-ctx"))

        assert_that(result).is_equal_to("value")
        assert_that(captured).is_equal_to(["the-ctx"])


class TestLazyResolveAsync:
    def test_resolve_awaits_coroutine_function(self) -> None:
        captured: list[object] = []

        async def resolver(ctx: object) -> str:
            captured.append(ctx)
            return "async-value"

        lazy: Lazy[str] = Lazy(resolver)
        result = asyncio.run(lazy.aresolve("ctx"))

        assert_that(result).is_equal_to("async-value")
        assert_that(captured).is_equal_to(["ctx"])

    def test_resolve_handles_resolver_returning_awaitable(self) -> None:
        async def inner() -> str:
            return "deferred"

        def resolver(ctx: object) -> Awaitable[str]:
            del ctx
            return inner()

        lazy: Lazy[str] = Lazy(resolver)
        result = asyncio.run(lazy.aresolve(None))

        assert_that(result).is_equal_to("deferred")


class TestLazyTyping:
    def test_lazy_is_generic_over_t(self) -> None:
        # PEP 695 generic Lazy[int] should be subscriptable without error.
        lazy_int: Lazy[int] = Lazy(lambda _ctx: 42)
        assert_that(asyncio.run(lazy_int.aresolve(None))).is_equal_to(42)


class TestLazyPublicReexport:
    def test_lazy_is_exported_from_pyrmit_core(self) -> None:
        from pyrmit import core

        assert_that(core.Lazy).is_equal_to(Lazy)
