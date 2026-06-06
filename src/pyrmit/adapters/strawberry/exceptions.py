"""Typed exceptions raised by the Strawberry adapter.

These exceptions propagate as Strawberry-recognized errors and serialize
with stable extension ``code`` values that clients can match on.
"""

from __future__ import annotations


class PermissionDenied(Exception):  # noqa: N818  -- matches GraphQL ecosystem naming
    """Raised by ``policy_guard`` for FORBIDDEN denial.

    GraphQL response: error with ``extensions.code = "FORBIDDEN"``.
    """


class ResourceNotFound(Exception):  # noqa: N818
    """Raised by ``policy_guard`` for NOT_FOUND denial.

    GraphQL response: error with ``extensions.code = "NOT_FOUND"``. The
    error shape is identical to "subject loader returned None" so the
    response cannot distinguish missing-vs-restricted -- this concealment
    is intentional and prevents existence-disclosure side channels.
    """
