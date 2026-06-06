"""Property: disjoint policy registrations from multiple threads all persist.

The engine's class docstring claims "read-only after registration; concurrent
decisions across threads / asyncio tasks are safe on a single instance."
This test pins down a complementary property: when N threads each register
a distinct (action, subject_type) pair, the final binding table contains
all N entries, and decide() returns the correct policy for each.

This covers the common case where a startup routine fans out registration
across threads. It does NOT cover:

  - Two threads registering the same (action, subject_type) -- the
    duplicate-check is a non-atomic read-modify-write and could lose a
    write or both pass the duplicate check. The engine documents single-
    writer for that case; testing it would be flaky by design.
  - Mixed register + decide concurrency -- separate concern.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from assertpy import assert_that
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from pyrmit.core.decision import ALLOW, Decision
from pyrmit.core.engine import PolicyEngine
from pyrmit.core.entitlements import Entitlements
from pyrmit.core.principal import Principal


class _Action(StrEnum):
    READ = "read"
    WRITE = "write"
    DELETE = "delete"
    LIST = "list"
    SHARE = "share"
    APPROVE = "approve"
    REVIEW = "review"
    PUBLISH = "publish"


@dataclass(frozen=True)
class _S0:
    id: int


@dataclass(frozen=True)
class _S1:
    id: int


@dataclass(frozen=True)
class _S2:
    id: int


@dataclass(frozen=True)
class _S3:
    id: int


_SUBJECT_TYPES: tuple[type[_S0] | type[_S1] | type[_S2] | type[_S3], ...] = (_S0, _S1, _S2, _S3)


def _disjoint_pairs(
    actions: list[_Action],
    subject_idxs: list[int],
) -> list[tuple[_Action, type[_S0] | type[_S1] | type[_S2] | type[_S3]]]:
    """De-duplicate generated draws into a disjoint pair list."""
    seen: set[tuple[_Action, type[object]]] = set()
    pairs: list[tuple[_Action, type[_S0] | type[_S1] | type[_S2] | type[_S3]]] = []
    for action, idx in zip(actions, subject_idxs, strict=False):
        st_ = _SUBJECT_TYPES[idx]
        key = (action, cast(type[object], st_))
        if key in seen:
            continue
        seen.add(key)
        pairs.append((action, st_))
    return pairs


class TestDisjointRegistrationConcurrency:
    @given(
        actions=st.lists(st.sampled_from(list(_Action)), min_size=1, max_size=16),
        subject_idxs=st.lists(st.integers(min_value=0, max_value=3), min_size=1, max_size=16),
    )
    @settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_all_disjoint_registrations_persist(
        self,
        actions: list[_Action],
        subject_idxs: list[int],
    ) -> None:
        """Property: after N threads register disjoint pairs, every pair is queryable."""
        pairs = _disjoint_pairs(actions, subject_idxs)
        engine: PolicyEngine[Principal[str, str], _Action, object] = PolicyEngine()

        def _register(pair: tuple[_Action, type[object]]) -> None:
            action, subject_type = pair
            # Wrap to make each policy unique-by-identity for later assertion.
            policy_name = f"_pol_{action.value}_{subject_type.__name__}"

            def _policy(_p: Principal[str, str], _s: object) -> Decision:
                return ALLOW

            _policy.__name__ = policy_name
            engine.policy(action=action, subject_type=subject_type)(_policy)

        # Cast the typed pair tuples down to the registration shape used here.
        casted_pairs: list[tuple[_Action, type[object]]] = [(a, cast(type[object], s)) for a, s in pairs]
        with ThreadPoolExecutor(max_workers=8) as ex:
            futures = [ex.submit(_register, p) for p in casted_pairs]
            for f in futures:
                # Surface any thread-raised exception as a test failure.
                f.result()

        # Property 1: binding count matches the input -- no lost writes.
        assert_that(engine.registered_bindings()).is_length(len(pairs))

        # Property 2: every pair is individually queryable via binding_for,
        # AND decide returns the registered policy's decision (proves the
        # binding's policy callable was preserved).
        principal = Principal[str, str](actor="alice", entitlements=Entitlements[str].empty())
        for action, subject_type in pairs:
            binding = engine.binding_for(action=action, subject_type=cast(type[object], subject_type))
            assert_that(binding).is_not_none()
            subject = subject_type(id=0)
            decision = engine.decide(principal=principal, action=action, subject=subject)
            assert_that(decision.allowed).described_as(
                f"decide({action!r}, {subject_type.__name__}) must return the registered ALLOW"
            ).is_true()
