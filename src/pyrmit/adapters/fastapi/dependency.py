"""``require_policy`` -- FastAPI dependency factory.

Loads the subject via an application-supplied loader, calls the engine,
and translates denials into HTTP responses (403 or 404, per the binding's
denial surface).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any

from fastapi import HTTPException, Request

from pyrmit.core.decision import Decision, DenialSurface
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import ConfigurationError

_HttpDetail = Mapping[str, object] | str | None


@dataclass(frozen=True, slots=True)
class HttpDenial:
    """A typed return value for ``null_mapper`` callables.

    The ``Decision`` → ``HttpDenial`` shape is cleaner than returning a
    raw ``Response`` because the dependency must convey its decision via
    ``HTTPException`` (FastAPI's standard short-circuit mechanism), which
    serializes ``detail`` as JSON and forwards ``headers`` verbatim.

    Attributes:
        status_code: The HTTP status code to surface.
        reason: Optional short stable identifier; used as the default
            ``detail`` body when ``detail`` is None.
        headers: Optional mapping of response headers to forward.
        detail: Optional override for the response body. When ``None``,
            ``HTTPException`` uses ``{"detail": reason}`` (the default
            FastAPI shape). When set, the value is serialized as JSON
            and replaces the default detail.
    """

    status_code: int
    reason: str | None = None
    headers: Mapping[str, str] | None = None
    detail: _HttpDetail = None


def _binding_denial_surface(
    engine: PolicyEngine[Any, Any, Any],
    action: Any,
    subject_type: type[Any],
) -> DenialSurface:
    """Read the binding's denial surface from the engine (O(1))."""
    binding = engine.binding_for(action=action, subject_type=subject_type)
    if binding is not None:
        # See the Strawberry adapter's equivalent comment: the explicit
        # type annotation defeats warn_return_any on the Any-typed
        # PolicyBinding chain.
        surface: DenialSurface = binding.denial_surface
        return surface
    # No binding registered -- decide() will return policy_not_registered,
    # which the FORBIDDEN-default mapping turns into a 403.
    return DenialSurface.FORBIDDEN


def _http_denial_to_exception(denial: HttpDenial, *, decision: Decision) -> HTTPException:
    """Translate an HttpDenial value into an HTTPException."""
    detail: _HttpDetail = denial.detail if denial.detail is not None else denial.reason or decision.reason
    headers_dict: dict[str, str] | None = dict(denial.headers) if denial.headers else None
    return HTTPException(
        status_code=denial.status_code,
        detail=detail,
        headers=headers_dict,
    )


def require_policy(
    *,
    engine: PolicyEngine[Any, Any, Any],
    action: Any,
    subject_type: type[Any],
    load_subject: Callable[[Request], Awaitable[Any | None]],
    get_principal: Callable[[Request], Awaitable[Any]],
    null_mapper: Callable[[Decision], HttpDenial] | None = None,
    metadata: Mapping[str, str] = MappingProxyType({}),
) -> Callable[..., Awaitable[None]]:
    """Build a FastAPI dependency that guards a route with a policy.

    Validate ``NULL`` denial requires a ``null_mapper`` -- raises
    :class:`ConfigurationError` at dependency-construction time
    (application startup) if the binding uses ``NULL`` and no
    ``null_mapper`` is supplied. Misconfiguration fails loudly at
    boot rather than silently at request time.

    Args:
        engine: The policy engine.
        action: The action enum value the binding governs.
        subject_type: The concrete subject class.
        load_subject: Async loader; returns the subject for the request,
            or ``None`` for missing-resource (HTTP 404 regardless of the
            binding's denial surface).
        get_principal: Async loader; returns the per-request principal.
        null_mapper: Optional mapper from a ``Decision`` to an
            ``HttpDenial``, required only when the binding uses
            ``DenialSurface.NULL``.
        metadata: Optional adapter-supplied audit metadata; values MUST
            be strings.

    Returns:
        A FastAPI dependency callable suitable for use in ``Depends(...)``.

    Raises:
        ConfigurationError: If the binding uses ``NULL`` denial without
            a ``null_mapper``.
    """
    surface = _binding_denial_surface(engine, action, subject_type)
    if surface is DenialSurface.NULL and null_mapper is None:
        msg = (
            f"NULL denial requires a null_mapper for FastAPI route "
            f"(action={action!r}, subject_type={subject_type.__name__!r})"
        )
        raise ConfigurationError(
            message=msg,
            binding=f"{subject_type.__name__}.{action}",
        )

    audit_metadata = metadata if metadata else None

    async def _dep(request: Request) -> None:
        principal = await get_principal(request)
        subject = await load_subject(request)
        if subject is None:
            # Missing subject -> 404 regardless of denial surface.
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND"})

        decision = await engine.adecide(
            principal=principal,
            action=action,
            subject=subject,
            metadata=audit_metadata,
        )
        if decision.allowed:
            return None

        if surface is DenialSurface.FORBIDDEN:
            raise HTTPException(
                status_code=403,
                detail={"code": "FORBIDDEN", "reason": decision.reason},
            )
        if surface is DenialSurface.NOT_FOUND:
            raise HTTPException(
                status_code=404,
                detail={"code": "NOT_FOUND"},
            )
        # surface is DenialSurface.NULL -- the constructor enforced that
        # null_mapper is not None.
        assert null_mapper is not None  # narrow: validated at startup
        raise _http_denial_to_exception(null_mapper(decision), decision=decision)

    return _dep
