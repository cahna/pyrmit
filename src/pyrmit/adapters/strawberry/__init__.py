"""Strawberry adapter -- single ``policy_guard`` field extension.

Install via ``pip install pyrmit[strawberry]``.
"""

from __future__ import annotations

from pyrmit.adapters.strawberry.exceptions import (
    PermissionDenied,
    ResourceNotFound,
)
from pyrmit.adapters.strawberry.factory import PolicyGuardFactory
from pyrmit.adapters.strawberry.guard import (
    DenyHandler,
    default_deny_handler,
    policy_guard,
    post_resolution_policy_guard,
)
from pyrmit.core.errors import ConfigurationError

__all__ = [
    "ConfigurationError",
    "DenyHandler",
    "PermissionDenied",
    "PolicyGuardFactory",
    "ResourceNotFound",
    "default_deny_handler",
    "policy_guard",
    "post_resolution_policy_guard",
]
