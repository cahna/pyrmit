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
# identity, then by the guard's ``principal_loader`` object itself:
# ``ctx -> {principal_loader: principal}``. The inner key ensures two
# guards built from factories with DIFFERENT principal loaders on the
# same request never share a cached principal -- without it, the second
# guard would silently observe the first loader's principal. Using the
# callable itself (callables are hashable) rather than ``id()`` avoids
# any id-reuse hazard from a loader being collected and its address
# reassigned. Values are garbage-collected with the context (typically
# when the request completes); using a ``WeakKeyDictionary`` means a
# singleton or shared context will defeat caching but cannot leak one
# user's principal to another user's request.
_principal_cache: WeakKeyDictionary[object, dict[Callable[..., Any], Any]] = WeakKeyDictionary()
_MISSING: Final[object] = object()

type DenyHandler = Callable[[Decision, DenialSurface], Exception]
"""Host hook mapping a deny ``Decision`` + ``DenialSurface`` to an exception.

Called for the ``FORBIDDEN`` and ``NOT_FOUND`` surfaces (``NULL`` never
raises). Lets a host application substitute its own exception taxonomy
(e.g. one carrying ``extensions.code`` for GraphQL clients) for pyrmit's
built-in :class:`PermissionDenied` / :class:`ResourceNotFound`.

A custom handler receiving ``DenialSurface.NOT_FOUND`` MUST produce
output indistinguishable from its missing-resource output: a
NOT_FOUND-surfaced DENIAL (a real resource the caller may not see) and a
genuine ABSENCE (no such resource) both arrive here, and if the handler
lets their differing ``decision.reason`` leak into the client-visible
error it reintroduces the existence side channel that NOT_FOUND exists
to close. The handler still receives the real ``Decision`` (with its
audit-grade reason) so it can log or branch internally -- just not emit
distinguishable output.

Construction-safety refusals (the mutation / subscription post-resolution
blocks) do NOT route through this handler: they raise pyrmit's own
:class:`PermissionDenied` directly, because they are configuration errors
detected before any policy decision exists to hand off.
"""

_SUBJECT_NOT_FOUND: Final[Decision] = Decision(allowed=False, reason="subject_not_found")


def default_deny_handler(decision: Decision, surface: DenialSurface) -> Exception:
    """Default mapping: ``PermissionDenied`` for FORBIDDEN, ``ResourceNotFound`` for NOT_FOUND.

    For NOT_FOUND the outward message is the CONSTANT ``"not_found"``,
    independent of ``decision.reason``. This is deliberate: a
    NOT_FOUND-surfaced DENIAL (e.g. reason ``"doc_private"``) and a
    genuine ABSENCE (reason ``"subject_not_found"`` /
    ``"subject_post_resolution_missing"``) MUST be indistinguishable to
    the client, or the differing messages let a caller tell
    restricted-from-missing -- the existence side channel this surface
    exists to close. The real ``decision.reason`` is preserved on the
    ``Decision`` for audit and is still handed to any CUSTOM
    ``deny_handler``; only this default handler's client-visible message
    is normalized.
    """
    if surface is DenialSurface.NOT_FOUND:
        return ResourceNotFound("not_found")
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
        surface_override: DenialSurface | None = None,
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
        self._surface_override = surface_override

    async def _resolve_engine(self, info: Info[Any, Any]) -> PolicyEngine[Any, Any, Any]:
        """Return the engine, awaiting the ``Lazy`` resolver if one was supplied."""
        if isinstance(self._engine, Lazy):
            return await self._engine.aresolve(info)
        return self._engine

    async def _resolve_principal(self, info: Info[Any, Any]) -> Any:
        """Return the per-request principal, cached per ``(context, principal_loader)``.

        Uses a module-level ``WeakKeyDictionary`` so the outer cache
        lifetime is bound to the context object (typically per-request);
        the inner mapping is additionally keyed by the ``principal_loader``
        callable itself so two guards on the same request with different
        loaders never share a cached principal. Contexts that don't
        support weak references fall through to the no-cache path --
        correct but slower.
        """
        ctx = info.context
        loader_key = self._principal_loader
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
        """Return this guard's denial surface: the per-guard override if set, else the binding's.

        ``surface_override`` (set via ``policy_guard(..., denial_surface=...)``
        or ``post_resolution_policy_guard(..., denial_surface=...)``) applies
        only to THIS guard attachment; the binding's own registered surface
        is untouched and other guards on the same binding are unaffected.
        """
        if self._surface_override is not None:
            return self._surface_override
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

    @staticmethod
    def _is_subscription(info: Info[Any, Any]) -> bool:
        """Return whether the current operation is a subscription.

        Defensive against ``info.operation`` being absent (some test or
        adapter contexts synthesize a bare ``Info``); treats an
        unavailable operation as "not a subscription".
        """
        try:
            return info.operation.operation is OperationType.SUBSCRIPTION
        except AttributeError:
            return False

    def _check_post_resolution_safe(self, info: Info[Any, Any]) -> None:
        """Refuse to run a post-resolution guard against a mutation or subscription.

        The post-resolution path runs the resolver BEFORE consulting the
        policy. Two operation kinds are refused, on different grounds:

        * **Subscriptions are refused UNCONDITIONALLY** (independent of
          ``read_only``). A subscription resolver returns a *stream*
          (async generator), not a value -- there is nothing for
          ``load_subject_after`` to inspect and the guard could never
          reach a decision, so ``read_only=False`` is not a coherent
          opt-out. Attach a pre-resolution guard instead.
        * **Mutations are refused only when ``read_only=True``** (the
          default). Here the resolver's side effect (DB write, payment,
          external call) would fire before authorization; ``read_only=
          False`` is a coherent opt-in when the caller accepts that
          ordering.
        """
        try:
            op_type = info.operation.operation
        except AttributeError:
            return
        if op_type is OperationType.SUBSCRIPTION:
            raise PermissionDenied(
                "post_resolution_guard_on_subscription_blocked: a post-resolution "
                "guard cannot run on a subscription operation -- the resolver "
                "returns a stream, so there is no resolved value for "
                "load_subject_after to authorize; attach a pre-resolution guard "
                "instead"
            )
        if self._read_only and op_type is OperationType.MUTATION:
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
            result = next_(source, info, **kwargs)
            if inspect.isawaitable(result):
                return await result
            # Async-generator (subscription) or plain value from a sync
            # resolver: the ALLOW decision was already made above, so hand
            # the stream/value back untouched -- awaiting an async generator
            # would raise TypeError before the stream ever starts.
            return result
        if surface is DenialSurface.NULL and self._is_subscription(info):
            # NULL means "redact the field value" -- but a subscription
            # resolver produces a *stream*, and there is no single value to
            # null out. Returning None here would make graphql-core raise
            # "Subscription field must return AsyncIterable. Received: None",
            # presenting a fail-closed deny as a server bug. Redaction
            # semantics don't exist for streams, so fall closed to FORBIDDEN.
            raise self._deny_handler(decision, DenialSurface.FORBIDDEN)
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
    denial_surface: DenialSurface | None = None,
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
        denial_surface: Optional per-guard override of the binding's
            registered :class:`DenialSurface`. Applies only to THIS
            field attachment -- the binding's own registered surface
            (and any other guard built against the same binding) is
            unaffected. Defaults to ``None``, which preserves the
            binding's own surface. Note: on a **subscription** operation
            a ``NULL`` surface has no meaning -- there is no single field
            value to redact in a stream -- so a NULL-surfaced deny on a
            subscription falls closed to ``FORBIDDEN`` (raising through
            ``deny_handler``) rather than returning ``None``.

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
        surface_override=denial_surface,
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
    denial_surface: DenialSurface | None = None,
) -> FieldExtension:
    """Strawberry field guard for post-resolution redaction.

    .. warning::

        The resolver executes BEFORE the authorization decision. This is
        appropriate for **read-only redaction** (the resolver returns a
        candidate value, the guard decides whether the caller may see it),
        and inappropriate for fields with side effects (mutations,
        external calls, payments). The default ``read_only=True`` refuses
        to run inside a mutation operation at request time, raising
        :class:`PermissionDenied` BEFORE the resolver runs. Pass
        ``read_only=False`` only if you explicitly accept that the
        resolver's side effects will fire before the decision is reached.

        Subscription operations are refused UNCONDITIONALLY -- regardless
        of ``read_only`` -- because a post-resolution guard can never work
        on a subscription: the resolver returns a stream, so there is no
        resolved value for ``load_subject_after`` to authorize. Attach a
        pre-resolution guard (``policy_guard(..., load_subject=...)``)
        instead; ``read_only=False`` is not an opt-out here.

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
        denial_surface: Optional per-guard override of the binding's
            registered :class:`DenialSurface`. Applies only to THIS
            field attachment. See :func:`policy_guard` -- including the
            note that a ``NULL`` surface falls closed to ``FORBIDDEN`` on
            subscription operations.

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
        surface_override=denial_surface,
    )
