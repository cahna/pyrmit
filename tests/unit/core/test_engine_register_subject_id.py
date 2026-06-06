"""Unit tests for PolicyEngine.register_subject_id."""

from __future__ import annotations

from dataclasses import dataclass

from assertpy import assert_that

from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import DuplicateResolverError


@dataclass(frozen=True)
class _Subject:
    id: int


class TestRegisterSubjectId:
    def test_register_first_time_succeeds(self) -> None:
        engine: PolicyEngine[object, str, _Subject] = PolicyEngine()
        engine.register_subject_id(
            subject_type=_Subject,
            resolver=lambda s: str(s.id),
        )
        # No exception raised; introspection has no bindings (we didn't
        # register any policies).
        assert_that(engine.registered_bindings()).is_length(0)

    def test_duplicate_registration_raises(self) -> None:
        engine: PolicyEngine[object, str, _Subject] = PolicyEngine()
        engine.register_subject_id(
            subject_type=_Subject,
            resolver=lambda s: str(s.id),
        )
        try:
            engine.register_subject_id(
                subject_type=_Subject,
                resolver=lambda s: f"id-{s.id}",
            )
        except DuplicateResolverError as err:
            assert_that(err.subject_type).is_equal_to(_Subject.__name__)
            return
        assert_that(False).described_as("expected DuplicateResolverError").is_true()
