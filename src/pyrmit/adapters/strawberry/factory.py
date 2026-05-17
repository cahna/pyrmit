"""``PolicyGuardFactory`` -- captures cross-cutting guard dependencies once.

Real applications attach :func:`policy_guard` to many fields, all of
which share the same engine and the same per-request principal loader.
``PolicyGuardFactory`` lets the consumer name those once and call
``.guard(...)`` / ``.post_resolution_guard(...)`` per field, partially
applying the engine + loader and delegating to the bare functions.

The factory is purely sugar over :func:`policy_guard` and
:func:`post_resolution_policy_guard`; both functions remain in the
public surface for one-off use and as the implementation the factory
forwards to.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info

from pyrmit.adapters.strawberry.guard import policy_guard, post_resolution_policy_guard
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.lazy import Lazy


@dataclass(frozen=True)
class PolicyGuardFactory:
    """Bundles an engine + principal loader for repeated guard construction.

    Attributes:
        engine: The policy engine to consult on every guarded field.
            Accepts a concrete :class:`PolicyEngine` or a
            :class:`pyrmit.core.Lazy` resolving to one at request time.
        principal_loader: Callable resolving the per-request principal
            from Strawberry ``Info``. May return the principal directly
            or an awaitable of it.
    """

    engine: PolicyEngine[Any, Any, Any] | Lazy[PolicyEngine[Any, Any, Any]]
    principal_loader: Callable[[Info[Any, Any]], Any | Awaitable[Any]]

    def guard(
        self,
        *,
        action: Any,
        subject_type: type[Any],
        load_subject: Callable[[Info[Any, Any], Mapping[str, Any]], Awaitable[Any | None]] | None = None,
        load_subject_from_source: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None = None,
        load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None = None,
        metadata: Mapping[str, str] = MappingProxyType({}),
    ) -> FieldExtension:
        """Build a pre-/from-source/post-resolution guard sharing this factory's deps.

        Forwards to :func:`policy_guard` -- see its docstring for the
        loader semantics and the exactly-one-loader invariant.
        """
        return policy_guard(
            engine=self.engine,
            principal_loader=self.principal_loader,
            action=action,
            subject_type=subject_type,
            load_subject=load_subject,
            load_subject_from_source=load_subject_from_source,
            load_subject_after=load_subject_after,
            metadata=metadata,
        )

    def post_resolution_guard(
        self,
        *,
        action: Any,
        subject_type: type[Any],
        load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]],
        metadata: Mapping[str, str] = MappingProxyType({}),
        read_only: bool = True,
    ) -> FieldExtension:
        """Build a post-resolution redaction guard sharing this factory's deps.

        Forwards to :func:`post_resolution_policy_guard` -- see its
        docstring for the ``read_only`` mutation-safety check.
        """
        return post_resolution_policy_guard(
            engine=self.engine,
            principal_loader=self.principal_loader,
            action=action,
            subject_type=subject_type,
            load_subject_after=load_subject_after,
            metadata=metadata,
            read_only=read_only,
        )
