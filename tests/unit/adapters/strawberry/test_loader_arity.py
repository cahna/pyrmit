"""policy_guard loader-arity validation at construction time."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from assertpy import assert_that

from pyrmit.adapters.strawberry import ConfigurationError, policy_guard
from pyrmit.core.engine import PolicyEngine


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    id: int


def _engine() -> PolicyEngine[object, _Action, _Subject]:
    return PolicyEngine[object, _Action, _Subject]()


def _stub_principal_loader(_info: object) -> object:
    return object()


class TestLoaderArity:
    def test_zero_loaders_raises(self) -> None:
        try:
            policy_guard(
                engine=_engine(),
                principal_loader=_stub_principal_loader,
                action=_Action.READ,
                subject_type=_Subject,
            )
        except ConfigurationError:
            return
        assert_that(False).described_as("expected ConfigurationError").is_true()

    def test_two_loaders_raises(self) -> None:
        async def _from_kwargs(_info: object, _kw: object) -> _Subject | None:
            return None

        async def _from_source(_src: object, _info: object) -> _Subject | None:
            return None

        try:
            policy_guard(
                engine=_engine(),
                principal_loader=_stub_principal_loader,
                action=_Action.READ,
                subject_type=_Subject,
                load_subject=_from_kwargs,
                load_subject_from_source=_from_source,
            )
        except ConfigurationError:
            return
        assert_that(False).described_as("expected ConfigurationError").is_true()

    def test_three_loaders_raises(self) -> None:
        async def _a(_info: object, _kw: object) -> _Subject | None:
            return None

        async def _b(_src: object, _info: object) -> _Subject | None:
            return None

        async def _c(_res: object, _info: object) -> _Subject | None:
            return None

        try:
            policy_guard(
                engine=_engine(),
                principal_loader=_stub_principal_loader,
                action=_Action.READ,
                subject_type=_Subject,
                load_subject=_a,
                load_subject_from_source=_b,
                load_subject_after=_c,
            )
        except ConfigurationError:
            return
        assert_that(False).described_as("expected ConfigurationError").is_true()

    def test_exactly_one_loader_succeeds(self) -> None:
        async def _loader(_info: object, _kw: object) -> _Subject | None:
            return None

        ext = policy_guard(
            engine=_engine(),
            principal_loader=_stub_principal_loader,
            action=_Action.READ,
            subject_type=_Subject,
            load_subject=_loader,
        )
        assert_that(ext).is_not_none()
