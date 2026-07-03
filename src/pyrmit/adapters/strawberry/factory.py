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

from pyrmit.adapters.strawberry.guard import DenyHandler, policy_guard, post_resolution_policy_guard
from pyrmit.core.decision import DenialSurface
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.lazy import Lazy


@dataclass(frozen=True)
class PolicyGuardFactory[PrincipalT, ActionT, SubjectT]:
    """Bundles an engine + principal loader for repeated guard construction.

    Generic over the same ``(PrincipalT, ActionT, SubjectT)`` triple as
    :class:`~pyrmit.core.engine.PolicyEngine`. The type parameters are
    inferred from the ``engine`` (and ``principal_loader``) arguments, so
    callers rarely spell them out; a factory built from a
    ``PolicyEngine[Principal[Actor, str], Action, Article]`` propagates
    those types onto every ``.guard(...)`` call, letting mypy reject a
    wrong ``action`` enum or a subject loader whose element type does not
    match ``subject_type``.

    Attributes:
        engine: The policy engine to consult on every guarded field.
            Accepts a concrete :class:`PolicyEngine` or a
            :class:`pyrmit.core.Lazy` resolving to one at request time.
        principal_loader: Callable resolving the per-request principal
            from Strawberry ``Info``. May return the principal directly
            or an awaitable of it.
        deny_handler: Optional hook mapping a deny ``Decision`` +
            ``DenialSurface`` to the exception raised for FORBIDDEN and
            NOT_FOUND denials. Applied to every guard built by this
            factory unless overridden per-call via ``.guard(...,
            deny_handler=...)`` / ``.post_resolution_guard(...,
            deny_handler=...)``. Defaults to
            :func:`pyrmit.adapters.strawberry.guard.default_deny_handler`.
    """

    engine: PolicyEngine[PrincipalT, ActionT, SubjectT] | Lazy[PolicyEngine[PrincipalT, ActionT, SubjectT]]
    principal_loader: Callable[[Info[Any, Any]], PrincipalT | Awaitable[PrincipalT]]
    deny_handler: DenyHandler | None = None

    def guard[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
        load_subject: Callable[[Info[Any, Any], Mapping[str, Any]], Awaitable[ST | None]] | None = None,
        load_subject_from_source: Callable[[Any, Info[Any, Any]], Awaitable[ST | None]] | None = None,
        load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[ST | None]] | None = None,
        metadata: Mapping[str, str] = MappingProxyType({}),
        deny_handler: DenyHandler | None = None,
        denial_surface: DenialSurface | None = None,
    ) -> FieldExtension:
        """Build a pre-/from-source/post-resolution guard sharing this factory's deps.

        Forwards to :func:`policy_guard` -- see its docstring for the
        loader semantics and the exactly-one-loader invariant.

        Generic in an **unbounded** ``ST`` matching the engine's
        ``policy()`` shape (see
        :meth:`pyrmit.core.engine.PolicyEngine.policy` for why the bound
        ``ST: SubjectT`` cannot be expressed): an engine parameterized
        over a union or marker-base ``SubjectT`` can still build guards
        against a concrete subtype. ``ST`` is pinned by ``subject_type``,
        so a loader whose element type does not match is rejected by
        mypy, while ``action`` is checked against the factory's
        ``ActionT``.

        Args:
            action: The action enum value the binding governs.
            subject_type: The concrete subject class the binding governs.
            load_subject: Optional pre-resolution loader from kwargs.
            load_subject_from_source: Optional pre-resolution loader from
                the parent ``source`` value.
            load_subject_after: Optional post-resolution loader from the
                resolver's return value.
            metadata: Optional adapter-supplied audit metadata.
            deny_handler: Per-call override of the factory's
                ``deny_handler``; defaults to the factory's own value.
            denial_surface: Optional per-call override of the binding's
                registered :class:`DenialSurface`, applying only to this
                one guard attachment. There is no factory-level default
                for this -- it is per-call only. See
                :func:`~pyrmit.adapters.strawberry.guard.policy_guard`.
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
            deny_handler=deny_handler if deny_handler is not None else self.deny_handler,
            denial_surface=denial_surface,
        )

    def post_resolution_guard[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
        load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[ST | None]],
        metadata: Mapping[str, str] = MappingProxyType({}),
        deny_handler: DenyHandler | None = None,
        read_only: bool = True,
        denial_surface: DenialSurface | None = None,
    ) -> FieldExtension:
        """Build a post-resolution redaction guard sharing this factory's deps.

        Forwards to :func:`post_resolution_policy_guard` -- see its
        docstring for the ``read_only`` mutation-safety check. Generic in
        the same unbounded ``ST`` as :meth:`guard`; ``ST`` is pinned by
        ``subject_type`` and ``action`` is checked against ``ActionT``.

        Args:
            action: The action enum value the binding governs.
            subject_type: The concrete subject class.
            load_subject_after: Post-resolution loader.
            metadata: Optional adapter-supplied audit metadata.
            deny_handler: Per-call override of the factory's
                ``deny_handler``; defaults to the factory's own value.
            read_only: When ``True`` (default), refuses to run inside a
                mutation operation.
            denial_surface: Optional per-call override of the binding's
                registered :class:`DenialSurface`, applying only to this
                one guard attachment. Per-call only; no factory-level
                default. See
                :func:`~pyrmit.adapters.strawberry.guard.post_resolution_policy_guard`.
        """
        return post_resolution_policy_guard(
            engine=self.engine,
            principal_loader=self.principal_loader,
            action=action,
            subject_type=subject_type,
            load_subject_after=load_subject_after,
            metadata=metadata,
            deny_handler=deny_handler if deny_handler is not None else self.deny_handler,
            read_only=read_only,
            denial_surface=denial_surface,
        )
