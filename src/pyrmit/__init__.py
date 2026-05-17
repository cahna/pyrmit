"""Pyrmit -- a typed, framework-agnostic policy engine and entitlement layer.

Public re-exports of the core types. Adapter and audit-store implementations
live under ``pyrmit.adapters`` and ``pyrmit.audit``; entitlement providers
live under ``pyrmit.entitlements``; testing helpers live under
``pyrmit.testing``.

This module also attaches a single ``logging.NullHandler`` to the
``pyrmit`` logger so that the library never imposes logging configuration
on its consumers.
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

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

try:
    __version__: str = version("pyrmit")
except PackageNotFoundError:  # pragma: no cover
    __version__ = "unknown"

PACKAGE_DIR: Path = Path(__file__).parent
"""Path to the package directory."""

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
    "__version__",
    "deny",
]

# Library-grade observability: attach exactly one NullHandler and do not
# call logging.basicConfig, so the host application's logging stack is
# untouched. Idempotent under repeated imports (defensive: avoid double-
# attaching during test reload).
_logger = logging.getLogger("pyrmit")
if not any(isinstance(h, logging.NullHandler) for h in _logger.handlers):
    _logger.addHandler(logging.NullHandler())
