"""Public re-exports of the framework-agnostic core."""

from __future__ import annotations

from pyrmit.core.audit import AuditEntry, AuditOutcome, AuditStore
from pyrmit.core.binding import PolicyBinding, PolicyFn
from pyrmit.core.decision import ALLOW, Decision, DenialSurface, deny
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.errors import (
    ConfigurationError,
    DuplicatePolicyError,
    DuplicateResolverError,
    InvalidSubjectTypeError,
)
from pyrmit.core.lazy import Lazy
from pyrmit.core.principal import Principal

__all__ = [
    "ALLOW",
    "AuditEntry",
    "AuditOutcome",
    "AuditStore",
    "ConfigurationError",
    "Decision",
    "DenialSurface",
    "DuplicatePolicyError",
    "DuplicateResolverError",
    "Entitlements",
    "InvalidSubjectTypeError",
    "Lazy",
    "PolicyBinding",
    "PolicyEngine",
    "PolicyFn",
    "Principal",
    "deny",
]
