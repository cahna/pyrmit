"""Policy-matrix helper for snapshot-friendly testing."""

from __future__ import annotations

from collections.abc import Sequence

from pyrmit.core.decision import Decision
from pyrmit.core.engine import PolicyEngine


def policy_matrix[PrincipalT, ActionT, SubjectT](
    *,
    engine: PolicyEngine[PrincipalT, ActionT, SubjectT],
    principals: Sequence[PrincipalT],
    actions: Sequence[ActionT],
    subjects: Sequence[SubjectT],
) -> dict[tuple[str, str, str], Decision]:
    """Evaluate every (principal, action, subject) combination.

    Args:
        engine: The policy engine.
        principals: Principals to test against.
        actions: Action enum values to test against.
        subjects: Subjects to test against.

    Returns:
        A mapping ``{(repr(principal), str(action), repr(subject)): Decision}``.
        The string keys make the mapping snapshot-friendly: it serializes
        deterministically with ``json.dumps(..., sort_keys=True)``.
    """
    matrix: dict[tuple[str, str, str], Decision] = {}
    for principal in principals:
        for action in actions:
            for subject in subjects:
                key = (repr(principal), str(action), repr(subject))
                matrix[key] = engine.decide(
                    principal=principal,
                    action=action,
                    subject=subject,
                )
    return matrix
