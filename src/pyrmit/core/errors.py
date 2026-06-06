"""Library error variants.

DuplicatePolicyError and DuplicateResolverError extend Exception because
they are raised at registration time, which is a misuse-of-the-library
failure mode rather than a runtime policy outcome.

ConfigurationError extends Exception because engine or adapter
misconfiguration (e.g. FastAPI NULL without a custom mapper, or
``audit_failure_mode='deny'`` paired with ``audit_allows=False``) is a
startup-time invariant violation.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class DuplicatePolicyError(Exception):
    """Raised on duplicate ``(action, subject_type)`` policy registration.

    Use ``engine.replace_policy(...)`` to intentionally override a binding.
    """

    action: str
    subject_type: str

    def __post_init__(self) -> None:
        """Initialize the underlying Exception message with structured context."""
        super().__init__(
            f"duplicate policy registration for action={self.action!r}, subject_type={self.subject_type!r}"
        )


@dataclass(frozen=True)
class DuplicateResolverError(Exception):
    """Raised on duplicate subject-id resolver registration."""

    subject_type: str

    def __post_init__(self) -> None:
        """Initialize the underlying Exception message with structured context."""
        super().__init__(f"duplicate subject-id resolver for subject_type={self.subject_type!r}")


@dataclass(frozen=True)
class ConfigurationError(Exception):
    """Raised on engine or adapter misconfiguration at application startup.

    The ``binding`` field is optional. Adapter call sites that have a
    specific ``(action, subject_type)`` context should pass it; engine and
    schema-construction errors that aren't tied to a single binding pass
    ``None`` (rendered as ``<unspecified>`` in the message).
    """

    message: str
    binding: str | None = None

    def __post_init__(self) -> None:
        """Initialize the underlying Exception message with structured context."""
        rendered_binding = self.binding if self.binding is not None else "<unspecified>"
        super().__init__(f"{self.message} (binding={rendered_binding!r})")


@dataclass(frozen=True)
class InvalidSubjectTypeError(Exception):
    """Raised when a ``policy()`` registration violates ``subject_base``.

    The engine's ``subject_base`` constructor parameter (optional) enables
    runtime checking that every registered ``subject_type`` is a subclass
    of the engine's expected base. The check exists because mypy 2.1 has
    a known gap on PEP 695 nested generic bounds (``[ST: SubjectT]`` where
    ``SubjectT`` is an outer class TypeVar), and the runtime check is the
    equivalent guard.
    """

    subject_type: str
    expected_base: str

    def __post_init__(self) -> None:
        """Initialize the underlying Exception message with structured context."""
        super().__init__(
            f"subject_type={self.subject_type!r} is not a subclass of "
            f"the engine's subject_base={self.expected_base!r}; "
            f"this binding would never fire and is rejected at registration"
        )
