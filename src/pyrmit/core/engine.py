"""The PolicyEngine -- typed, generic over (PrincipalT, ActionT, SubjectT).

The engine is generic over three application-defined type parameters and
is declared using PEP 695 generic syntax so that bounds and constraints
live at the point of declaration and the public typing surface remains
machine-checkable end-to-end.
"""

from __future__ import annotations

import datetime
import logging
import sys
from collections.abc import Callable, Mapping
from typing import Final, Literal, TypeAliasType, cast, get_args

# uuid7 source: stdlib on Python 3.14+, uuid-utils' compat module otherwise.
# Both surfaces return standard ``uuid.UUID`` instances. The
# ``uuid-utils`` package is declared with a ``python_version < '3.14'``
# marker in pyproject.toml so it is only installed on Python 3.12 / 3.13.
if sys.version_info >= (3, 14):
    from uuid import uuid7  # pragma: no cover -- exercised on 3.14+ CI matrix
else:
    from uuid_utils.compat import uuid7

from pyrmit.core.audit import AuditEntry, AuditOutcome, AuditStore
from pyrmit.core.binding import PolicyBinding, PolicyFn
from pyrmit.core.decision import Decision, DenialSurface, DetailValue
from pyrmit.core.errors import (
    ConfigurationError,
    DuplicatePolicyError,
    DuplicateResolverError,
    InvalidSubjectTypeError,
)

_LOGGER: Final[logging.Logger] = logging.getLogger("pyrmit.core.engine")

_DENY_POLICY_NOT_REGISTERED: Final[Decision] = Decision(allowed=False, reason="policy_not_registered")
_DENY_POLICY_ERROR: Final[Decision] = Decision(allowed=False, reason="policy_error")
_DENY_AUDIT_UNAVAILABLE: Final[Decision] = Decision(allowed=False, reason="audit_unavailable")


class PolicyEngine[PrincipalT, ActionT, SubjectT]:
    """Typed policy engine generic over principal, action, and subject types.

    Construct, register subject-id resolvers, register policies via the
    ``policy`` decorator factory, then call ``decide`` (sync, no I/O) or
    ``adecide`` (async, with audit dispatch) from the request hot path.

    The engine is read-only after registration; concurrent decisions across
    threads / asyncio tasks are safe on a single instance.
    """

    __slots__ = (
        "_actor_id",
        "_audit",
        "_audit_failure_mode",
        "_audit_outcomes",
        "_bindings",
        "_request_id_for",
        "_subject_base",
        "_subject_id_resolvers",
    )

    def __init__(
        self,
        *,
        audit: AuditStore | None = None,
        audit_denies: bool = True,
        audit_allows: bool = False,
        audit_errors: bool = True,
        audit_failure_mode: Literal["log", "deny"] = "log",
        actor_id: Callable[[PrincipalT], str | None] | None = None,
        request_id_for: Callable[[PrincipalT], str | None] | None = None,
        subject_base: (type[SubjectT] | tuple[type[SubjectT], ...] | TypeAliasType | None) = None,
    ) -> None:
        """Construct a policy engine.

        Args:
            audit: Optional ``AuditStore`` for ``adecide`` to dispatch entries
                to. If ``None``, ``adecide`` mirrors ``decide`` exactly.
            audit_denies: Whether to audit deny decisions. Default ``True``.
            audit_allows: Whether to audit allow decisions. Default ``False``.
            audit_errors: Whether to audit decisions caused by a policy
                exception. Default ``True``.
            audit_failure_mode: How to handle ``AuditStore.write`` failures.
                ``"log"`` (default) logs at WARNING and returns the original
                decision; ``"deny"`` returns ``Decision(allowed=False,
                reason="audit_unavailable")``.
            actor_id: Optional callable resolving a ``PrincipalT`` to a string
                identifier for audit entries. Returning ``None`` is allowed
                and yields an absent ``AuditEntry.actor_id``.
            request_id_for: Optional callable resolving a ``PrincipalT`` to
                a per-request correlation identifier for audit entries.
                When omitted, ``AuditEntry.request_id`` is ``None``. The
                engine treats ``PrincipalT`` as opaque -- we do NOT
                duck-type-extract ``principal.request_id``. Callers using
                the built-in ``Principal[A, E]`` typically pass
                ``request_id_for=lambda p: p.request_id``.
            subject_base: Optional runtime guard. When supplied, every
                ``policy()`` / ``replace_policy()`` / ``register_subject_id()``
                call asserts the ``subject_type`` is a subclass of one of
                the configured bases, raising
                :class:`InvalidSubjectTypeError` on mismatch. Three forms
                are supported, covering both supported subject-type
                parameterization patterns:

                * **Single class** (marker-base pattern):
                  ``subject_base=Subject``.
                * **Tuple of classes** (union pattern, explicit):
                  ``subject_base=(MatchSubject, ClubSubject)``.
                * **PEP 695 type alias** (union pattern, auto-extracted):
                  ``subject_base=AppSubject`` where
                  ``type AppSubject = MatchSubject | ClubSubject``. The
                  engine inspects the alias's resolved value and pulls
                  out the concrete classes via ``typing.get_args``.

                mypy 2.1 cannot enforce the ``ST <: SubjectT`` bound on
                ``policy()`` (a known PEP 695 gap with nested generic
                constraints); this guard is the runtime equivalent and
                catches orphan registrations at registration time instead
                of leaving them as silent dead code.
        """
        self._audit: AuditStore | None = audit
        self._audit_failure_mode: Literal["log", "deny"] = audit_failure_mode
        self._actor_id: Callable[[PrincipalT], str | None] | None = actor_id
        self._request_id_for: Callable[[PrincipalT], str | None] | None = request_id_for
        self._subject_base: tuple[type[object], ...] | None = self._normalize_subject_base(subject_base)

        outcomes: set[AuditOutcome] = set()
        if audit_allows:
            outcomes.add(AuditOutcome.ALLOWED)
        if audit_denies:
            outcomes.add(AuditOutcome.DENIED)
        if audit_errors:
            outcomes.add(AuditOutcome.ERROR)
        self._audit_outcomes: frozenset[AuditOutcome] = frozenset(outcomes)

        # Fail-closed invariant: ``audit_failure_mode="deny"`` only protects
        # outcomes that actually go through the audit write path. With the
        # default ``audit_allows=False``, ALLOWs short-circuit before the
        # write, silently bypassing the deny-on-audit-failure contract.
        # Require the caller to make the trade-off explicit.
        if audit_failure_mode == "deny" and AuditOutcome.ALLOWED not in outcomes:
            raise ConfigurationError(
                message=(
                    "audit_failure_mode='deny' requires audit_allows=True so "
                    "that allow decisions are covered by the deny-on-failure "
                    "invariant. Pass audit_allows=True to opt in (every allow "
                    "becomes an audit write), or use audit_failure_mode='log' "
                    "if you accept that audit-store failures degrade silently "
                    "for allows."
                ),
                binding=None,
            )

        # Registration tables. Written at startup only; read on every decide.
        self._bindings: dict[
            tuple[ActionT, type[SubjectT]],
            PolicyBinding[PrincipalT, ActionT, SubjectT],
        ] = {}
        self._subject_id_resolvers: dict[type[SubjectT], Callable[[SubjectT], str | None]] = {}

    # ----------------------------------------------------------------- registration

    def register_subject_id[ST](
        self,
        *,
        subject_type: type[ST],
        resolver: Callable[[ST], str | None],
    ) -> None:
        """Register a subject-id resolver for one concrete subject type.

        The ``ST`` TypeVar is intentionally **unbounded** rather than
        ``ST: SubjectT``. Bounded form is rejected by both mypy and
        pyright when ``SubjectT`` is an outer TypeVar (a known limitation
        across PEP 695 implementations as of 2026), which made the
        union / marker-base subject-type patterns fail to compile. The
        unbounded form trades a registration-time type-level guard (which
        neither checker can enforce anyway) for the library's documented
        user-facing typing patterns. Runtime safety remains: the engine dispatches
        only when ``(action, type(subject))`` matches a binding's
        registered key, so a resolver registered for the wrong subject
        type silently never fires rather than producing an unsafe match.

        Args:
            subject_type: The concrete subject class. SHOULD be a subtype
                of the engine's ``SubjectT`` parameter; consistency is
                NOT enforced at registration time.
            resolver: A callable that maps a subject of type ``ST`` to an
                identifier string (or ``None``).

        Raises:
            DuplicateResolverError: If a resolver for ``subject_type`` is
                already registered.
        """
        self._check_subject_base(subject_type)
        # Cast through the wider SubjectT key so the resolver table can
        # store all registered resolvers uniformly. See the method
        # docstring above for why this is the right shape.
        widened_subject_type = cast("type[SubjectT]", subject_type)
        if widened_subject_type in self._subject_id_resolvers:
            raise DuplicateResolverError(subject_type=subject_type.__name__)
        self._subject_id_resolvers[widened_subject_type] = cast("Callable[[SubjectT], str | None]", resolver)

    def policy[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
        denial_surface: DenialSurface = DenialSurface.FORBIDDEN,
    ) -> Callable[
        [PolicyFn[PrincipalT, ST]],
        PolicyFn[PrincipalT, ST],
    ]:
        """Register a policy for one ``(action, subject_type)`` pair.

        Generic in an **unbounded** ``ST`` so that an engine parameterized
        over a union type or a marker base class can register policies
        against concrete subtypes (e.g. ``MatchSubject`` when the engine is
        ``PolicyEngine[..., MatchSubject | ClubSubject]``). See
        ``register_subject_id`` for the rationale -- both mypy and pyright
        reject ``ST: SubjectT`` when ``SubjectT`` is an outer TypeVar, so
        we trade the compile-time bound (which neither checker can enforce)
        for the documented subject-type patterns. Runtime safety remains: bindings
        are keyed on ``(action, type(subject))``, so a policy registered
        for a wrong ``subject_type`` silently never fires.

        Args:
            action: The action enum value.
            subject_type: The concrete subject class. SHOULD be a subtype
                of the engine's ``SubjectT`` parameter; consistency is
                NOT enforced at registration time.
            denial_surface: How a deny should surface to the calling adapter.
                Default ``DenialSurface.FORBIDDEN``.

        Returns:
            A decorator that registers the wrapped function and returns it
            unchanged for normal use.

        Raises:
            DuplicatePolicyError: If a policy is already registered for the
                same ``(action, subject_type)`` pair. Use ``replace_policy``
                to override intentionally.
        """

        def _decorator(
            fn: PolicyFn[PrincipalT, ST],
        ) -> PolicyFn[PrincipalT, ST]:
            widened_subject_type = cast("type[SubjectT]", subject_type)
            if (action, widened_subject_type) in self._bindings:
                raise DuplicatePolicyError(
                    action=str(action),
                    subject_type=subject_type.__name__,
                )
            self._register_binding(
                action=action,
                subject_type=subject_type,
                policy=fn,
                denial_surface=denial_surface,
            )
            return fn

        return _decorator

    def replace_policy[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
        denial_surface: DenialSurface = DenialSurface.FORBIDDEN,
    ) -> Callable[
        [PolicyFn[PrincipalT, ST]],
        PolicyFn[PrincipalT, ST],
    ]:
        """Register or replace the policy for one ``(action, subject_type)`` pair.

        Same unbounded-``ST`` signature as ``policy`` -- but never raises
        on duplicate. Use for test overrides and environment-specific
        rule replacements.
        """

        def _decorator(
            fn: PolicyFn[PrincipalT, ST],
        ) -> PolicyFn[PrincipalT, ST]:
            self._register_binding(
                action=action,
                subject_type=subject_type,
                policy=fn,
                denial_surface=denial_surface,
            )
            return fn

        return _decorator

    @staticmethod
    def _normalize_subject_base(
        base: (type[SubjectT] | tuple[type[SubjectT], ...] | TypeAliasType | None),
    ) -> tuple[type[object], ...] | None:
        """Normalize a ``subject_base`` argument into a tuple of classes.

        Supports four input shapes:

        1. ``None`` (disabled) -> returns ``None``.
        2. A single class -> wrapped in a one-element tuple.
        3. A tuple of classes (explicit union) -> returned as-is
           after validating every element is a class.
        4. A PEP 695 ``TypeAliasType`` (union alias, auto-extracted) ->
           members extracted via ``typing.get_args(base.__value__)``.
           Both PEP 604 ``A | B`` and ``typing.Union[A, B]`` are supported;
           nested unions like ``A | (B | C)`` are auto-flattened by
           Python. Single-member aliases (``type T = A``) are also
           supported: ``get_args`` returns ``()`` and the resolved
           ``__value__`` IS the class, which is wrapped into ``(A,)``.

        **Strict validation, no silent drops.** Every member MUST be a
        class. The first non-class element (forward-reference string,
        ``Literal[...]``, generic alias like ``list[A]``, etc.) raises
        :class:`ConfigurationError` with an index and the runtime type
        of the bad element so the caller can fix it directly. Empty
        inputs also raise. The guard exists to catch wrong-shape inputs
        loudly -- silently filtering would corrupt the very property the
        guard is configured to protect.

        Raises:
            ConfigurationError: On empty input, a tuple/union member that
                isn't a class, or an unsupported input type.
        """
        if base is None:
            return None
        if isinstance(base, type):
            return (cast("type[object]", base),)
        if isinstance(base, tuple):
            if not base:
                raise ConfigurationError(
                    message=(
                        "subject_base tuple is empty; supply at least one "
                        "class (or omit subject_base entirely to disable "
                        "the guard)"
                    ),
                    binding=None,
                )
            return PolicyEngine._validate_class_sequence(
                base,
                source_description="subject_base tuple",
            )
        if isinstance(base, TypeAliasType):
            return PolicyEngine._normalize_type_alias(base)
        # The static type system narrows out the legal forms above; this
        # branch fires only when a caller bypasses typing with Any.
        raise ConfigurationError(
            message=(
                f"subject_base of type {type(base).__name__!r} is not "
                f"supported; pass a class, a tuple of classes, or a "
                f"PEP 695 type alias"
            ),
            binding=None,
        )

    @staticmethod
    def _normalize_type_alias(
        alias: TypeAliasType,
    ) -> tuple[type[object], ...]:
        """Extract concrete classes from a PEP 695 ``TypeAliasType``.

        Three sub-shapes are accepted:

        1. ``type T = A | B`` (PEP 604 union) -> ``get_args`` returns
           ``(A, B)``; both are validated as classes.
        2. ``type T = Union[A, B]`` (legacy Union) -> same as above.
        3. ``type T = A`` (single member) -> ``get_args`` returns ``()``
           and ``__value__`` IS the class; wrap into ``(A,)``.

        Raises:
            ConfigurationError: If the alias resolves to a non-class
                (e.g. forward-reference string, generic alias).
        """
        args = get_args(alias.__value__)
        if not args:
            # Single-member alias case: __value__ IS the class itself.
            value: object = alias.__value__
            if isinstance(value, type):
                return (cast("type[object]", value),)
            raise ConfigurationError(
                message=(
                    f"subject_base TypeAliasType {alias.__name__!r} "
                    f"resolves to {value!r} "
                    f"(runtime type: {type(value).__name__}), which is "
                    f"neither a class nor a union of classes. Pass an "
                    f"explicit tuple of classes instead."
                ),
                binding=None,
            )
        return PolicyEngine._validate_class_sequence(
            args,
            source_description=(f"subject_base TypeAliasType {alias.__name__!r} (resolved to {alias.__value__!r})"),
        )

    @staticmethod
    def _validate_class_sequence(
        members: tuple[object, ...],
        *,
        source_description: str,
    ) -> tuple[type[object], ...]:
        """Validate every element of ``members`` is a class; raise otherwise.

        Args:
            members: The tuple to validate. Each element MUST be a
                ``type``; non-class elements raise.
            source_description: Human-readable description of where
                ``members`` came from; used in the error message.

        Returns:
            A non-empty tuple of classes, in input order.

        Raises:
            ConfigurationError: If any element is not a class. The error
                message names the offending element's index and runtime
                type so the user can fix it directly.
        """
        normalized: list[type[object]] = []
        for index, member in enumerate(members):
            if not isinstance(member, type):
                raise ConfigurationError(
                    message=(
                        f"{source_description} contains a non-class "
                        f"element at index [{index}]: {member!r} "
                        f"(runtime type: {type(member).__name__}). "
                        f"Forward-reference strings, Literal[...], "
                        f"generic aliases like list[A], and other "
                        f"non-class members are NOT silently dropped. "
                        f"Replace them with the concrete class."
                    ),
                    binding=None,
                )
            normalized.append(cast("type[object]", member))
        return tuple(normalized)

    def _check_subject_base(self, subject_type: type[object]) -> None:
        """Runtime guard: raise if ``subject_type`` is not under ``subject_base``.

        The mypy 2.1 PEP 695 nested-bound limitation means the engine
        cannot statically enforce that ``ST <: SubjectT`` on registration
        calls. This runtime check is the equivalent guard, opted into by
        passing ``subject_base=...`` to the engine constructor. Without
        it, an orphan registration (e.g. ``subject_type=int`` on an
        engine parameterized over a Subject base) silently never fires
        -- which is a security regression masquerading as "fail closed".
        """
        if self._subject_base is None:
            return
        if not issubclass(subject_type, self._subject_base):
            expected = " | ".join(b.__name__ for b in self._subject_base)
            raise InvalidSubjectTypeError(
                subject_type=subject_type.__name__,
                expected_base=expected,
            )

    def _register_binding[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
        policy: PolicyFn[PrincipalT, ST],
        denial_surface: DenialSurface,
    ) -> None:
        """Internal helper: store the binding behind the engine's wider type.

        Callable is contravariant in its argument, so a Callable[[ST], ...]
        is NOT structurally a Callable[[SubjectT], ...] for the wider
        SubjectT. We store the narrower binding behind the wider key
        type with a cast -- the engine dispatches only when the runtime
        ``type(subject)`` matches the registered key, so the call is
        always type-safe in practice. The cast sites are the narrowly
        scoped boundary where the engine reconciles per-subject policy
        types with its wider generic shape.
        """
        self._check_subject_base(subject_type)
        widened_policy = cast("PolicyFn[PrincipalT, SubjectT]", policy)
        widened_subject_type = cast("type[SubjectT]", subject_type)
        binding: PolicyBinding[PrincipalT, ActionT, SubjectT] = PolicyBinding(
            action=action,
            subject_type=widened_subject_type,
            policy=widened_policy,
            denial_surface=denial_surface,
        )
        self._bindings[(action, widened_subject_type)] = binding

    # ----------------------------------------------------------------- decisions

    def decide(
        self,
        *,
        principal: PrincipalT,
        action: ActionT,
        subject: SubjectT,
    ) -> Decision:
        """Synchronously evaluate a policy.

        Pure; never raises; runs no I/O. Missing binding -> ``policy_not_registered``;
        policy body exception -> ``policy_error``. A policy exception is also
        logged at WARNING (with ``exc_info=True``) on the ``pyrmit.core.engine``
        logger -- a raising policy body is treated as noteworthy by default,
        not something that requires opting into DEBUG to observe.

        Args:
            principal: The caller's principal value.
            action: The action enum value.
            subject: The subject of the action.

        Returns:
            A ``Decision`` value.
        """
        binding = self._bindings.get((action, type(subject)))
        if binding is None:
            return _DENY_POLICY_NOT_REGISTERED
        try:
            return binding.policy(principal, subject)
        except Exception:
            _LOGGER.warning(
                "policy raised; converting to deny reason=policy_error action=%r subject_type=%r",
                action,
                type(subject).__name__,
                exc_info=True,
            )
            return _DENY_POLICY_ERROR

    async def adecide(
        self,
        *,
        principal: PrincipalT,
        action: ActionT,
        subject: SubjectT,
        metadata: Mapping[str, DetailValue] | None = None,
    ) -> Decision:
        """Async evaluate a policy with optional audit dispatch.

        Identical to ``decide`` except that the configured ``AuditStore``
        (if any) receives an ``AuditEntry`` for every outcome in the
        configured audit-outcomes set. Audit-store failures are handled
        per ``audit_failure_mode``.

        Args:
            principal: The caller's principal value.
            action: The action enum value.
            subject: The subject of the action.
            metadata: Optional adapter- or caller-supplied metadata that
                is attached to the emitted ``AuditEntry.metadata``.
                Values MUST be ``str``, ``int``, or ``bool``; the
                ``AuditEntry`` constructor enforces this at runtime.

        Returns:
            A ``Decision`` value.
        """
        decision = self.decide(
            principal=principal,
            action=action,
            subject=subject,
        )
        if self._audit is None:
            return decision
        outcome = self._outcome_for(decision)
        if outcome not in self._audit_outcomes:
            return decision

        binding = self._bindings.get((action, type(subject)))
        denial_surface_value: str | None = binding.denial_surface.value if binding is not None else None
        entry = self._build_audit_entry(
            principal=principal,
            action=action,
            subject=subject,
            decision=decision,
            outcome=outcome,
            denial_surface_value=denial_surface_value,
            metadata=metadata,
        )
        try:
            await self._audit.write(entry)
        except Exception:
            _LOGGER.warning(
                "audit store write failed action=%r outcome=%r",
                action,
                outcome.value,
                exc_info=True,
            )
            if self._audit_failure_mode == "deny":
                return _DENY_AUDIT_UNAVAILABLE
        return decision

    # ----------------------------------------------------------------- internals

    @staticmethod
    def _outcome_for(decision: Decision) -> AuditOutcome:
        """Map a Decision to its audit outcome category."""
        if decision.allowed:
            return AuditOutcome.ALLOWED
        if decision.reason == "policy_error":
            return AuditOutcome.ERROR
        return AuditOutcome.DENIED

    def _build_audit_entry(
        self,
        *,
        principal: PrincipalT,
        action: ActionT,
        subject: SubjectT,
        decision: Decision,
        outcome: AuditOutcome,
        denial_surface_value: str | None,
        metadata: Mapping[str, DetailValue] | None,
    ) -> AuditEntry:
        """Construct an AuditEntry from a decided request.

        Args:
            principal: The caller's principal.
            action: The action enum value.
            subject: The subject of the action.
            decision: The ``Decision`` returned by the policy.
            outcome: The audit outcome category.
            denial_surface_value: The binding's denial surface value (string
                form) or ``None`` if no binding existed.
            metadata: Optional adapter-supplied metadata; values MUST be
                ``str``, ``int``, or ``bool``. Passing ``None`` produces
                an empty mapping.
        """
        validated_metadata: Mapping[str, DetailValue]
        validated_metadata = dict(metadata) if metadata is not None else {}

        # Explicit resolver -- the engine treats PrincipalT as opaque and
        # does NOT duck-type-extract attributes. Callers using the built-in
        # ``Principal[A, E]`` pass
        # ``request_id_for=lambda p: p.request_id`` to the constructor.
        request_id: str | None = self._request_id_for(principal) if self._request_id_for is not None else None

        actor_id = self._actor_id(principal) if self._actor_id is not None else None

        subject_resolver = self._subject_id_resolvers.get(type(subject))
        subject_id: str | None = subject_resolver(subject) if subject_resolver is not None else None

        u7 = uuid7()
        return AuditEntry(
            id=str(u7).replace("-", ""),
            timestamp=datetime.datetime.now(tz=datetime.UTC),
            outcome=outcome,
            action=str(action),
            subject_type=type(subject).__name__,
            subject_id=subject_id,
            actor_id=actor_id,
            reason=decision.reason,
            denial_surface=denial_surface_value,
            request_id=request_id,
            metadata=validated_metadata,
        )

    # ----------------------------------------------------------------- introspection

    def binding_for[ST](
        self,
        *,
        action: ActionT,
        subject_type: type[ST],
    ) -> PolicyBinding[PrincipalT, ActionT, ST] | None:
        """Look up the binding (policy + denial surface) for a pair.

        Generic in unbounded ``ST`` (matching ``policy()``'s shape) so
        callers can request a narrower binding and receive a
        ``PolicyBinding`` parameterized over the narrower type. See
        ``policy()`` for the unbounded-TypeVar rationale.

        Returns:
            The matching ``PolicyBinding[..., ST]`` when one is registered,
            otherwise ``None``.
        """
        widened_subject_type = cast("type[SubjectT]", subject_type)
        binding = self._bindings.get((action, widened_subject_type))
        if binding is None:
            return None
        # Symmetric cast: we registered behind the wider engine type, so
        # narrowing back here is the inverse of the storage-time widening.
        return cast(
            "PolicyBinding[PrincipalT, ActionT, ST]",
            binding,
        )

    def registered_bindings(
        self,
    ) -> tuple[PolicyBinding[PrincipalT, ActionT, SubjectT], ...]:
        """Return every registered binding in registration order."""
        return tuple(self._bindings.values())
