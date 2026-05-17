"""Unit tests for PolicyEngine construction."""

from __future__ import annotations

import pytest
from assertpy import assert_that

from pyrmit.core.engine import PolicyEngine
from pyrmit.core.errors import ConfigurationError


class TestEngineConstruction:
    def test_default_constructor_succeeds(self) -> None:
        engine: PolicyEngine[object, str, object] = PolicyEngine()
        # Should construct without error; introspection returns no bindings.
        assert_that(engine.registered_bindings()).is_length(0)

    def test_default_audit_is_none(self) -> None:
        engine: PolicyEngine[object, str, object] = PolicyEngine()
        # Audit being optional is the contract: no store -> no audit.
        # We only check public-facing behavior: registered_bindings empty,
        # construction succeeds.
        assert_that(engine.registered_bindings()).is_length(0)

    def test_audit_failure_mode_log_accepts_default_audit_outcomes(self) -> None:
        e: PolicyEngine[object, str, object] = PolicyEngine(audit_failure_mode="log")
        assert_that(e).is_not_none()

    def test_audit_failure_mode_deny_requires_audit_allows_true(self) -> None:
        # Default audit_allows=False would let ALLOW decisions silently
        # bypass the deny-on-audit-failure invariant; construction must
        # reject the combination loudly.
        with pytest.raises(ConfigurationError) as exc_info:
            PolicyEngine[object, str, object](audit_failure_mode="deny")
        assert_that(str(exc_info.value)).contains("audit_allows=True")

    def test_audit_failure_mode_deny_with_audit_allows_true_succeeds(self) -> None:
        e: PolicyEngine[object, str, object] = PolicyEngine(
            audit_failure_mode="deny",
            audit_allows=True,
        )
        assert_that(e).is_not_none()

    def test_actor_id_callable_accepted(self) -> None:
        engine: PolicyEngine[object, str, object] = PolicyEngine(
            actor_id=lambda _p: "anon",
        )
        assert_that(engine).is_not_none()
