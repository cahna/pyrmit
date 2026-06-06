"""Policy-function type alias and the runtime PolicyBinding record."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pyrmit.core.decision import Decision, DenialSurface

type PolicyFn[PrincipalT, SubjectT] = Callable[[PrincipalT, SubjectT], Decision]
"""A pure, synchronous policy function: (principal, subject) -> Decision.

Policy bodies MUST NOT perform I/O. Exceptions raised by a policy body are
caught by the engine and converted to ``Decision(allowed=False,
reason="policy_error")``.
"""


@dataclass(frozen=True)
class PolicyBinding[PrincipalT, ActionT, SubjectT]:
    """The runtime record pairing a policy function with its registration.

    Attributes:
        action: The action enum value the binding governs.
        subject_type: The concrete subject type the binding governs.
        policy: The registered ``PolicyFn``.
        denial_surface: How a deny from ``policy`` should surface to the
            calling adapter.
    """

    action: ActionT
    subject_type: type[SubjectT]
    policy: PolicyFn[PrincipalT, SubjectT]
    denial_surface: DenialSurface
