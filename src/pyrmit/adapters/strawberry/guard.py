"""``policy_guard`` -- the single Strawberry field extension.

One extension owns subject loading, decision, and denial enforcement
together. There is no permission-class API that could be misused to
split denial enforcement across hooks; the unified extension forecloses
the historical "split-gate" inactive-resource leak in which a separate
permission step ran before subject loading and silently revealed
existence via a different error code.
"""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable, Mapping
from types import MappingProxyType
from typing import Any, Final
from weakref import WeakKeyDictionary

from graphql.language.ast import OperationType
from strawberry.extensions.field_extension import FieldExtension
from strawberry.types import Info

from pyrmit.adapters.strawberry.exceptions import (
    PermissionDenied,
    ResourceNotFound,
)
from pyrmit.core.decision import Decision, DenialSurface
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import ConfigurationError
from pyrmit.core.lazy import Lazy

# Per-request principal cache. Keyed by the request's ``info.context``
# identity, then by the guard's ``principal_loader`` identity: ``ctx ->
# {id(principal_loader): principal}``. The inner key ensures two guards
# built from factories with DIFFERENT principal loaders on the same
# request never share a cached principal -- without it, the second
# guard would silently observe the first loader's principal. Loader
# lifetimes are module/factory scope, so ``id()`` reuse is not a
# concern within a live request. Values are garbage-collected with the
# context (typically when the request completes); using a
# ``WeakKeyDictionary`` means a singleton or shared context will defeat
# caching but cannot leak one user's principal to another user's
# request.
_principal_cache: WeakKeyDictionary[object, dict[int, Any]] = WeakKeyDictionary()
_MISSING: Final[object] = object()

type DenyHandler = Callable[[Decision, DenialSurface], Exception]
"""Host hook mapping a deny ``Decision`` + ``DenialSurface`` to an exception.

Called for the ``FORBIDDEN`` and ``NOT_FOUND`` surfaces (``NULL`` never
raises). Lets a host application substitute its own exception taxonomy
(e.g. one carrying ``extensions.code`` for GraphQL clients) for pyrmit's
built-in :class:`PermissionDenied` / :class:`ResourceNotFound`.
"""

_SUBJECT_NOT_FOUND: Final[Decision] = Decision(allowed=False, reason="subject_not_found")


def default_deny_handler(decision: Decision, surface: DenialSurface) -> Exception:
    """Default mapping: ``PermissionDenied`` for FORBIDDEN, ``ResourceNotFound`` for NOT_FOUND.

    Preserves pyrmit's historical behavior for hosts that don't supply
    their own ``deny_handler``.
    """
    if surface is DenialSurface.NOT_FOUND:
        return ResourceNotFound(decision.reason or "not_found")
    return PermissionDenied(decision.reason or "forbidden")


class _PolicyGuard(FieldExtension):
    """Internal FieldExtension implementing the policy_guard semantics."""

    def __init__(
        self,
        *,
        engine: PolicyEngine[Any, Any, Any] | Lazy[PolicyEngine[Any, Any, Any]],
        principal_loader: Callable[[Info[Any, Any]], Any | Awaitable[Any]],
        action: Any,
        subject_type: type[Any],
        load_subject: Callable[[Info[Any, Any], Mapping[str, Any]], Awaitable[Any | None]] | None,
        load_subject_from_source: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None,
        load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None,
        metadata: Mapping[str, str],
        deny_handler: DenyHandler,
        read_only: bool = True,
    ) -> None:
        """Construct the extension. Loader arity is validated by ``policy_guard``."""
        self._engine = engine
        self._principal_loader = principal_loader
        self._action = action
        self._subject_type = subject_type
        self._load_subject = load_subject
        self._load_subject_from_source = load_subject_from_source
        self._load_subject_after = load_subject_after
        self._metadata = metadata
        self._deny_handler = deny_handler
        self._read_only = read_only

    async def _resolve_engine(self, info: Info[Any, Any]) -> PolicyEngine[Any, Any, Any]:
        """Return the engine, awaiting the ``Lazy`` resolver if one was supplied."""
        if isinstance(self._engine, Lazy):
            return await self._engine.aresolve(info)
        return self._engine

    async def _resolve_principal(self, info: Info[Any, Any]) -> Any:
        """Return the per-request principal, cached per ``(context, principal_loader)``.

        Uses a module-level ``WeakKeyDictionary`` so the outer cache
        lifetime is bound to the context object (typically per-request);
        the inner mapping is additionally keyed by ``id(principal_loader)``
        so two guards on the same request with different loaders never
        share a cached principal. Contexts that don't support weak
        references fall through to the no-cache path -- correct but
        slower.
        """
        ctx = info.context
        loader_key = id(self._principal_loader)
        try:
            per_ctx = _principal_cache.get(ctx)
        except TypeError:
            # Some context types reject ``__hash__`` or ``__eq__`` against
            # WeakKeyDictionary; fall through to fresh resolution.
            per_ctx = None
        cached = per_ctx.get(loader_key, _MISSING) if per_ctx is not None else _MISSING
        if cached is not _MISSING:
            return cached
        result = self._principal_loader(info)
        principal = await result if inspect.isawaitable(result) else result
        try:
            _principal_cache.setdefault(ctx, {})[loader_key] = principal
        except TypeError:
            # Context isn't weak-refable (e.g. a plain ``dict``);
            # caching is an optimization, not a correctness requirement.
            pass
        return principal

    def _binding_denial_surface(self, engine: PolicyEngine[Any, Any, Any]) -> DenialSurface:
        """Look up the configured denial surface for this binding (O(1))."""
        binding = engine.binding_for(
            action=self._action,
            subject_type=self._subject_type,
        )
        if binding is not None:
            # The explicit annotation satisfies ``warn_return_any`` over the
            # adapter's Any-typed PolicyBinding chain; the .denial_surface
            # field is concretely typed so this is structurally a no-op.
            surface: DenialSurface = binding.denial_surface
            return surface
        # No binding registered -> the engine returns policy_not_registered
        # at decide() time; default to FORBIDDEN for the missing-policy case.
        return DenialSurface.FORBIDDEN

    def _apply_denial(self, decision: Decision, surface: DenialSurface) -> Any:
        """Translate a deny decision into the configured framework signal.

        ``NULL`` returns ``None`` (field-level redaction); ``FORBIDDEN`` and
        ``NOT_FOUND`` raise whatever ``self._deny_handler`` returns, letting
        the host substitute its own exception taxonomy for pyrmit's
        built-in :class:`PermissionDenied` / :class:`ResourceNotFound`.
        """
        if surface is DenialSurface.NULL:
            return None
        raise self._deny_handler(decision, surface)

    def _check_post_resolution_safe(self, info: Info[Any, Any]) -> None:
        """Refuse to run a post-resolution guard against a mutation operation.

        The post-resolution path runs the resolver BEFORE consulting the
        policy. For mutation operations that means a side effect (DB write,
        payment, external call) executes before authorization is checked.
        ``read_only=True`` (the default for ``post_resolution_policy_guard``)
        refuses this combination at request time; ``read_only=False``
        opts in explicitly.
        """
        if not self._read_only:
            return
        try:
            op_type = info.operation.operation
        except AttributeError:
            return
        if op_type is OperationType.MUTATION:
            raise PermissionDenied(
                "post_resolution_guard_on_mutation_blocked: this guard runs the "
                "resolver before authorization; pass read_only=False to accept "
                "that the mutation's side effect will fire before the decision"
            )

    async def resolve_async(
        self,
        next_: Callable[..., Awaitable[Any]],
        source: Any,
        info: Info[Any, Any],
        **kwargs: Any,
    ) -> Any:
        """Run subject load + decision + denial enforcement around ``next_``."""
        principal = await self._resolve_principal(info)
        engine = await self._resolve_engine(info)
        surface = self._binding_denial_surface(engine)
        # ``self._metadata`` is the immutable adapter-supplied audit
        # metadata; ``None`` lets the engine produce an empty mapping.
        metadata = self._metadata if self._metadata else None

        # Phase: post-resolution -- run resolver first, then load + decide.
        if self._load_subject_after is not None:
            self._check_post_resolution_safe(info)
            result = await next_(source, info, **kwargs)
            subject = await self._load_subject_after(result, info)
            if subject is None:
                # The resolved value yields no subject to decide against:
                # treat as "no resource" per the contract.
                raise self._deny_handler(
                    Decision(allowed=False, reason="subject_post_resolution_missing"),
                    DenialSurface.NOT_FOUND,
                )
            decision = await engine.adecide(
                principal=principal,
                action=self._action,
                subject=subject,
                metadata=metadata,
            )
            if decision.allowed:
                return result
            return self._apply_denial(decision, surface)

        # Phase: pre-resolution (from source or from kwargs).
        if self._load_subject_from_source is not None:
            subject = await self._load_subject_from_source(source, info)
        else:
            assert self._load_subject is not None  # narrow: arity validated
            subject = await self._load_subject(info, kwargs)

        if subject is None:
            # Missing subject is NOT a guarded denial -- it's an absence,
            # and absence always surfaces as NOT_FOUND regardless of the
            # binding's denial surface.
            raise self._deny_handler(_SUBJECT_NOT_FOUND, DenialSurface.NOT_FOUND)

        decision = await engine.adecide(
            principal=principal,
            action=self._action,
            subject=subject,
            metadata=metadata,
        )
        if decision.allowed:
            return await next_(source, info, **kwargs)
        return self._apply_denial(decision, surface)


def policy_guard(
    *,
    engine: PolicyEngine[Any, Any, Any] | Lazy[PolicyEngine[Any, Any, Any]],
    principal_loader: Callable[[Info[Any, Any]], Any | Awaitable[Any]],
    action: Any,
    subject_type: type[Any],
    load_subject: Callable[[Info[Any, Any], Mapping[str, Any]], Awaitable[Any | None]] | None = None,
    load_subject_from_source: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None = None,
    load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]] | None = None,
    metadata: Mapping[str, str] = MappingProxyType({}),
    deny_handler: DenyHandler | None = None,
) -> FieldExtension:
    """Construct a Strawberry FieldExtension that guards a field with a policy.

    Exactly one of ``load_subject``, ``load_subject_from_source``, or
    ``load_subject_after`` MUST be provided. Specifying zero or more than
    one raises :class:`ConfigurationError` at schema-construction time so
    that misconfiguration fails loudly at boot rather than silently at
    request time.

    Args:
        engine: The policy engine to consult. Either a concrete
            :class:`PolicyEngine` (captured at schema-construction
            time) or a :class:`pyrmit.core.Lazy` wrapping a resolver
            that receives Strawberry ``Info`` and returns the engine
            (for dependency-injection scenarios where the engine lives
            on the per-request context).
        principal_loader: Callable that resolves the per-request
            principal. Receives the Strawberry ``Info`` and returns
            either a concrete principal or an awaitable of one; the
            adapter normalizes both forms. Result is cached per
            ``(info.context, principal_loader)`` identity, so multiple
            guarded fields on a single request that share the same
            loader share a single resolution, while guards built with
            different loaders never observe each other's principal.
        action: The action enum value the binding governs.
        subject_type: The concrete subject class the binding governs.
        load_subject: Optional pre-resolution loader from kwargs.
        load_subject_from_source: Optional pre-resolution loader from the
            parent ``source`` value.
        load_subject_after: Optional post-resolution loader from the
            resolver's return value (for fields whose subject depends on
            the resolved value). Because the resolver runs before the
            decision in this mode, mutation operations are blocked by
            default. Use ``post_resolution_policy_guard(...,
            read_only=False)`` only when you explicitly accept that
            ordering.
        metadata: Optional adapter-supplied audit metadata. Values MUST
            be strings.
        deny_handler: Optional hook mapping a deny ``Decision`` +
            ``DenialSurface`` to the exception to raise for FORBIDDEN and
            NOT_FOUND denials (``NULL`` always returns ``None``). Defaults
            to :func:`default_deny_handler`, which raises pyrmit's
            built-in :class:`PermissionDenied` / :class:`ResourceNotFound`.

    Returns:
        A :class:`FieldExtension` ready to attach via
        ``@strawberry.field(extensions=[policy_guard(...)])``.

    Raises:
        ConfigurationError: If the loader arity is wrong.
    """
    loaders_supplied = [
        load_subject is not None,
        load_subject_from_source is not None,
        load_subject_after is not None,
    ]
    count = sum(loaders_supplied)
    if count != 1:
        msg = (
            f"policy_guard requires exactly one of load_subject, "
            f"load_subject_from_source, or load_subject_after to be "
            f"provided (got {count})"
        )
        raise ConfigurationError(message=msg)

    return _PolicyGuard(
        engine=engine,
        principal_loader=principal_loader,
        action=action,
        subject_type=subject_type,
        load_subject=load_subject,
        load_subject_from_source=load_subject_from_source,
        load_subject_after=load_subject_after,
        metadata=metadata,
        deny_handler=deny_handler if deny_handler is not None else default_deny_handler,
        # Pre-resolution paths are always safe -- the policy decides
        # before any resolver-side-effect can fire. The legacy
        # ``load_subject_after`` path is post-resolution, so it shares
        # the default mutation block with ``post_resolution_policy_guard``.
        read_only=load_subject_after is not None,
    )


def post_resolution_policy_guard(
    *,
    engine: PolicyEngine[Any, Any, Any] | Lazy[PolicyEngine[Any, Any, Any]],
    principal_loader: Callable[[Info[Any, Any]], Any | Awaitable[Any]],
    action: Any,
    subject_type: type[Any],
    load_subject_after: Callable[[Any, Info[Any, Any]], Awaitable[Any | None]],
    metadata: Mapping[str, str] = MappingProxyType({}),
    deny_handler: DenyHandler | None = None,
    read_only: bool = True,
) -> FieldExtension:
    """Strawberry field guard for post-resolution redaction.

    .. warning::

        The resolver executes BEFORE the authorization decision. This is
        appropriate for **read-only redaction** (the resolver returns a
        candidate value, the guard decides whether the caller may see it),
        and inappropriate for fields with side effects (mutations,
        external calls, payments). The default ``read_only=True`` blocks
        attachment to mutation operations at request time, raising
        :class:`PermissionDenied` BEFORE the resolver runs. Pass
        ``read_only=False`` only if you explicitly accept that the
        resolver's side effects will fire before the decision is reached.

    Behaviorally equivalent to ``policy_guard(..., load_subject_after=fn)``
    with the additional ``read_only`` safety check. Use this when the
    subject of the policy decision is the *value* the resolver returns
    (e.g. for field-level redaction based on the resolved object).

    Args:
        engine: The policy engine to consult.
        principal_loader: Callable resolving the per-request principal
            from Strawberry ``Info``. See :func:`policy_guard`.
        action: The action enum value the binding governs.
        subject_type: The concrete subject class.
        load_subject_after: Post-resolution loader; takes the resolver's
            return value plus ``Info`` and returns the subject to check
            (or ``None`` to surface NOT_FOUND).
        metadata: Optional adapter-supplied audit metadata. Values MUST
            be strings.
        deny_handler: Optional hook mapping a deny ``Decision`` +
            ``DenialSurface`` to the exception to raise for FORBIDDEN and
            NOT_FOUND denials. See :func:`policy_guard`.
        read_only: When ``True`` (default), refuses to run inside a
            mutation operation. Set to ``False`` to opt out -- only do
            this if the resolver has no observable side effect.

    Returns:
        A :class:`FieldExtension` ready to attach via
        ``@strawberry.field(extensions=[post_resolution_policy_guard(...)])``.
    """
    return _PolicyGuard(
        engine=engine,
        principal_loader=principal_loader,
        action=action,
        subject_type=subject_type,
        load_subject=None,
        load_subject_from_source=None,
        load_subject_after=load_subject_after,
        metadata=metadata,
        deny_handler=deny_handler if deny_handler is not None else default_deny_handler,
        read_only=read_only,
    )
