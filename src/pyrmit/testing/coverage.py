"""Coverage assertions: verify the engine has the policies you expect."""

from __future__ import annotations

from pyrmit.core.engine import PolicyEngine


def assert_policy_registered[PrincipalT, ActionT, SubjectT](
    *,
    engine: PolicyEngine[PrincipalT, ActionT, SubjectT],
    action: ActionT,
    subject_type: type[SubjectT],
) -> None:
    """Assert that ``engine`` has a policy for ``(action, subject_type)``.

    Args:
        engine: The policy engine.
        action: The action enum value.
        subject_type: The concrete subject class -- MUST be the same type
            (or a subtype) that the engine is parameterized over.

    Raises:
        AssertionError: If no policy is registered for the pair.
    """
    # Use registered_bindings() instead of binding_for() to avoid a
    # TypeVar contravariance friction with mypy: binding_for is generic
    # over [ST: SubjectT] which mypy cannot trivially bind to the helper's
    # own SubjectT parameter; iterating the binding list sidesteps the
    # issue and keeps the helper's contract honest.
    for binding in engine.registered_bindings():
        if binding.action == action and binding.subject_type is subject_type:
            return
    msg = f"no policy registered for action={action!r}, subject_type={subject_type.__name__!r}"
    raise AssertionError(msg)
