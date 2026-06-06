"""Runtime subject_base guard.

Background: mypy 2.1 has a known gap on PEP 695 nested generic bounds
(``[ST: SubjectT]`` where ``SubjectT`` is an outer class TypeVar) -- it
emits ``[type-var]: Value of type variable "ST" of policy of PolicyEngine
cannot be "A"`` even though ``A`` is structurally a subtype of the engine's
``SubjectT``. We work around the gap with an unbounded method ``[ST]``
TypeVar (which makes the union and marker-base patterns compile), and we
provide a runtime ``subject_base`` guard for opt-in registration-time
checking. This file verifies the guard catches the orphan-registration
footgun: registering a ``subject_type`` that the engine never decides on.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Union

from assertpy import assert_that

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import ConfigurationError, InvalidSubjectTypeError

# Used inside type aliases that legacy-Union the underscored test classes.
_ = Union


class _Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class _Subject:
    """Marker base for the engine."""


@dataclass(frozen=True)
class _Article(_Subject):
    id: int


@dataclass(frozen=True)
class _UnrelatedType:
    """A type that is NOT a subclass of _Subject; should fail the guard."""

    payload: str


class TestSubjectBaseGuard:
    def test_unrelated_subject_type_rejected_at_registration(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            subject_base=_Subject,
        )

        # Decorator MUST raise at decoration time, not at first decide().
        try:

            @engine.policy(action=_Action.READ, subject_type=_UnrelatedType)
            def _orphan(_p: object, _s: _UnrelatedType) -> Decision:
                return ALLOW

        except InvalidSubjectTypeError as err:
            assert_that(err.subject_type).is_equal_to("_UnrelatedType")
            assert_that(err.expected_base).is_equal_to("_Subject")
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError on orphan registration").is_true()

    def test_valid_subclass_passes(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            subject_base=_Subject,
        )

        @engine.policy(action=_Action.READ, subject_type=_Article)
        def _read_article(_p: object, _s: _Article) -> Decision:
            return ALLOW

        # No raise; the binding is registered.
        assert_that(engine.registered_bindings()).is_length(1)

    def test_register_subject_id_also_guards(self) -> None:
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine(
            subject_base=_Subject,
        )

        try:
            engine.register_subject_id(
                subject_type=_UnrelatedType,
                resolver=lambda s: s.payload,
            )
        except InvalidSubjectTypeError:
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError on orphan resolver registration").is_true()

    def test_no_subject_base_allows_anything(self) -> None:
        """Without subject_base, the guard is disabled."""
        engine: PolicyEngine[object, _Action, _Subject] = PolicyEngine()

        @engine.policy(action=_Action.READ, subject_type=_UnrelatedType)
        def _whatever(_p: object, _s: _UnrelatedType) -> Decision:
            return ALLOW

        assert_that(engine.registered_bindings()).is_length(1)


# ----------------------------------------------------------- union-pattern coverage


@dataclass(frozen=True)
class _MatchSubject:
    match_id: int


@dataclass(frozen=True)
class _ClubSubject:
    club_id: int


# PEP 695 type alias -- the engine should auto-extract members.
type _AppSubject = _MatchSubject | _ClubSubject


class TestSubjectBaseGuardPatternATuple:
    """Union pattern end-to-end with subject_base as an explicit tuple."""

    def test_tuple_form_accepts_member_classes(self) -> None:
        engine: PolicyEngine[object, _Action, _AppSubject] = PolicyEngine(
            subject_base=(_MatchSubject, _ClubSubject),
        )

        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _read_match(_p: object, _s: _MatchSubject) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.READ, subject_type=_ClubSubject)
        def _read_club(_p: object, _s: _ClubSubject) -> Decision:
            return ALLOW

        assert_that(engine.registered_bindings()).is_length(2)

    def test_tuple_form_rejects_non_member(self) -> None:
        engine: PolicyEngine[object, _Action, _AppSubject] = PolicyEngine(
            subject_base=(_MatchSubject, _ClubSubject),
        )

        try:

            @engine.policy(action=_Action.READ, subject_type=_UnrelatedType)
            def _orphan(_p: object, _s: _UnrelatedType) -> Decision:
                return ALLOW

        except InvalidSubjectTypeError as err:
            assert_that(err.subject_type).is_equal_to("_UnrelatedType")
            # Expected-base is rendered as a union string for the tuple form.
            assert_that(err.expected_base).contains("_MatchSubject")
            assert_that(err.expected_base).contains("_ClubSubject")
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError").is_true()


class TestSubjectBaseGuardPatternATypeAlias:
    """Union pattern end-to-end with subject_base as a PEP 695 TypeAliasType."""

    def test_type_alias_form_auto_extracts_members(self) -> None:
        # Pass the type alias directly; the engine extracts members via
        # typing.get_args on its resolved value.
        engine: PolicyEngine[object, _Action, _AppSubject] = PolicyEngine(
            subject_base=_AppSubject,
        )

        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _read_match(_p: object, _s: _MatchSubject) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.READ, subject_type=_ClubSubject)
        def _read_club(_p: object, _s: _ClubSubject) -> Decision:
            return ALLOW

        # Both bindings register; both decide correctly.
        assert_that(engine.registered_bindings()).is_length(2)

        match_d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_MatchSubject(match_id=1),
        )
        club_d = engine.decide(
            principal=object(),
            action=_Action.READ,
            subject=_ClubSubject(club_id=2),
        )
        assert_that(match_d.allowed).is_true()
        assert_that(club_d.allowed).is_true()

    def test_type_alias_form_rejects_non_member(self) -> None:
        engine: PolicyEngine[object, _Action, _AppSubject] = PolicyEngine(
            subject_base=_AppSubject,
        )

        try:

            @engine.policy(action=_Action.READ, subject_type=_UnrelatedType)
            def _orphan(_p: object, _s: _UnrelatedType) -> Decision:
                return ALLOW

        except InvalidSubjectTypeError as err:
            assert_that(err.subject_type).is_equal_to("_UnrelatedType")
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError").is_true()


# ----------------------------------------------------------- normalizer edge cases


# Module-level type aliases for the edge-case tests below.
type _LegacyUnion = _MatchSubject | _ClubSubject  # PEP 604
type _NestedUnion = _MatchSubject | (_ClubSubject | _Article)
type _SingleMember = _MatchSubject
type _ForwardRefs = Union["_MatchSubject", "_ClubSubject"]  # noqa: F821, UP007
type _GenericMembers = list[_MatchSubject] | dict[str, _ClubSubject]


class TestNormalizerStrictValidation:
    """The normalizer MUST raise on non-class members rather than silently
    drop them. The guard's whole purpose is to catch wrong-shape inputs
    loudly; silent filtering would defeat the guard.
    """

    def test_tuple_with_string_typo_raises(self) -> None:
        """A common typo: ``subject_base=(MatchSubject, "ClubSubject")``.

        The prior implementation silently dropped the string and produced
        a half-broken guard. The new implementation MUST raise with a
        precise message naming the offender.
        """
        try:
            PolicyEngine[object, _Action, _Subject](
                subject_base=(_MatchSubject, "ClubSubject"),  # type: ignore[arg-type]
            )
        except ConfigurationError as err:
            assert_that(str(err)).contains("non-class element at index [1]")
            assert_that(str(err)).contains("str")  # the offender's runtime type
            return
        assert_that(False).described_as("expected ConfigurationError on string-in-tuple").is_true()

    def test_empty_tuple_raises(self) -> None:
        try:
            PolicyEngine[object, _Action, _Subject](
                subject_base=(),
            )
        except ConfigurationError as err:
            assert_that(str(err)).contains("tuple is empty")
            return
        assert_that(False).described_as("expected ConfigurationError on empty tuple").is_true()

    def test_tuple_with_generic_alias_raises(self) -> None:
        """list[MatchSubject] is NOT a class -- it's a types.GenericAlias.
        Must raise, not silently drop.
        """
        try:
            PolicyEngine[object, _Action, _Subject](
                subject_base=(_MatchSubject, list[_MatchSubject]),  # type: ignore[arg-type]
            )
        except ConfigurationError as err:
            assert_that(str(err)).contains("non-class element at index [1]")
            return
        assert_that(False).described_as("expected ConfigurationError on generic alias in tuple").is_true()

    def test_legacy_union_form_accepted(self) -> None:
        """``type T = Union[A, B]`` is structurally identical to PEP 604."""
        engine: PolicyEngine[object, _Action, _LegacyUnion] = PolicyEngine(
            subject_base=_LegacyUnion,
        )

        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _pol(_p: object, _s: _MatchSubject) -> Decision:
            return ALLOW

        assert_that(engine.registered_bindings()).is_length(1)

    def test_nested_union_is_auto_flattened(self) -> None:
        """Python auto-flattens ``A | (B | C)`` to ``A | B | C``;
        the normalizer inherits this behavior via ``typing.get_args``.
        """
        engine: PolicyEngine[object, _Action, _NestedUnion] = PolicyEngine(
            subject_base=_NestedUnion,
        )

        # All three member types register without error.
        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _m(_p: object, _s: _MatchSubject) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.READ, subject_type=_ClubSubject)
        def _c(_p: object, _s: _ClubSubject) -> Decision:
            return ALLOW

        @engine.policy(action=_Action.READ, subject_type=_Article)
        def _a(_p: object, _s: _Article) -> Decision:
            return ALLOW

        assert_that(engine.registered_bindings()).is_length(3)

    def test_single_member_alias_accepted(self) -> None:
        """``type T = A`` is a single-member alias; ``get_args`` returns
        ``()`` but ``__value__`` IS the class. Normalizer wraps into
        ``(A,)``.
        """
        engine: PolicyEngine[object, _Action, _SingleMember] = PolicyEngine(
            subject_base=_SingleMember,
        )

        @engine.policy(action=_Action.READ, subject_type=_MatchSubject)
        def _pol(_p: object, _s: _MatchSubject) -> Decision:
            return ALLOW

        # Orphan registration is rejected against the single-member alias.
        try:

            @engine.policy(action=_Action.READ, subject_type=_ClubSubject)
            def _orphan(_p: object, _s: _ClubSubject) -> Decision:
                return ALLOW

        except InvalidSubjectTypeError as err:
            assert_that(err.subject_type).is_equal_to("_ClubSubject")
            return
        assert_that(False).described_as("expected InvalidSubjectTypeError on non-member registration").is_true()

    def test_alias_with_forward_refs_raises(self) -> None:
        """``type T = Union["A", "B"]`` contains ``ForwardRef`` members;
        they are NOT classes, so the normalizer rejects them.
        """
        try:
            PolicyEngine[object, _Action, _Subject](
                subject_base=_ForwardRefs,
            )
        except ConfigurationError as err:
            assert_that(str(err)).contains("non-class element")
            assert_that(str(err)).contains("ForwardRef")
            return
        assert_that(False).described_as("expected ConfigurationError on forward-ref alias").is_true()

    def test_alias_with_generic_members_raises(self) -> None:
        """``type T = list[A] | dict[str, B]`` contains generic aliases
        (``types.GenericAlias``), not classes. Normalizer raises.
        """
        try:
            PolicyEngine[object, _Action, _Subject](
                subject_base=_GenericMembers,
            )
        except ConfigurationError as err:
            assert_that(str(err)).contains("non-class element")
            return
        assert_that(False).described_as("expected ConfigurationError on generic-alias members").is_true()
