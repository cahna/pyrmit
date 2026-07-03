"""Typed exceptions raised by the Strawberry adapter.

These are the *default* exceptions ``policy_guard`` raises for FORBIDDEN
and NOT_FOUND denials. They serialize as plain GraphQL errors -- Strawberry
does not attach an ``extensions.code`` to them automatically. Hosts that
want a stable machine-readable error code (or their own exception
taxonomy entirely) should supply a ``deny_handler`` to ``policy_guard`` /
``post_resolution_policy_guard`` / ``PolicyGuardFactory``, which is
invoked in place of raising these directly.
"""

from __future__ import annotations


class PermissionDenied(Exception):  # noqa: N818  -- matches GraphQL ecosystem naming
    """Default exception raised by ``policy_guard`` for FORBIDDEN denial.

    Serializes as a plain GraphQL error message. Supply a ``deny_handler``
    to raise a different exception (e.g. one carrying a structured error
    code) instead.
    """


class ResourceNotFound(Exception):  # noqa: N818
    """Default exception raised by ``policy_guard`` for NOT_FOUND denial.

    Serializes as a plain GraphQL error message, identical in shape to
    "subject loader returned None" -- the response cannot distinguish
    missing-vs-restricted -- this concealment is intentional and prevents
    existence-disclosure side channels. Supply a ``deny_handler`` to raise
    a different exception instead.
    """
