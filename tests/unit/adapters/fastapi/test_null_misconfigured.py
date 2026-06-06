"""NULL denial without null_mapper raises ConfigurationError at startup."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.adapters.fastapi import ConfigurationError, require_policy
from pyrmit.core.decision import ALLOW, Decision, DenialSurface
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


class TestNullMisconfigured:
    def test_null_without_mapper_raises_at_dependency_construction(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(
            action=_Action.READ,
            subject_type=_Subject,
            denial_surface=DenialSurface.NULL,
        )
        def _pol(_p: object, _s: _Subject) -> Decision:
            return ALLOW

        async def _loader(request: object) -> _Subject | None:
            del request
            return None

        async def _principal(request: object) -> object:
            del request
            return object()

        try:
            require_policy(
                engine=engine,
                action=_Action.READ,
                subject_type=_Subject,
                load_subject=_loader,
                get_principal=_principal,
                # null_mapper deliberately omitted.
            )
        except ConfigurationError as err:
            assert_that(err.binding).contains("_Subject")
            return
        assert_that(False).described_as("expected ConfigurationError").is_true()
