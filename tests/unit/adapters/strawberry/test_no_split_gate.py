"""No split-gate API: NULL denial cannot be expressed via permission-class hooks."""

from __future__ import annotations

from assertpy import assert_that

import pyrmit.adapters.strawberry as adapter


class TestNoSplitGateAPI:
    def test_public_surface_does_not_export_permission_class(self) -> None:
        """The adapter MUST NOT expose any name that smells like a
        permission-class API (the historical pattern where a hook
        returns True/False and the resolver is expected to mask).
        """
        public_names = [n for n in dir(adapter) if not n.startswith("_")]
        # Allowlist the documented public surface.
        documented = {
            "ConfigurationError",
            "DenyHandler",
            "PermissionDenied",
            "PolicyGuardFactory",
            "ResourceNotFound",
            "default_deny_handler",
            "policy_guard",
            "post_resolution_policy_guard",
            # Re-exported submodules (importable but not in __all__).
            "exceptions",
            "factory",
            "guard",
            # `from __future__ import annotations` bleeds through dir().
            "annotations",
        }
        unexpected = set(public_names) - documented
        assert_that(unexpected).described_as(f"unexpected public names: {unexpected!r}").is_empty()

    def test_no_permission_class_name_in_exports(self) -> None:
        forbidden_substrings = ["Permission", "Hook", "Gate"]
        # PermissionDenied IS an export (the denial exception).
        # We're checking for *classes that could be misused as gates*,
        # not the typed-exception class itself.
        # A permission-class API would have something like `BasePermission`
        # or `HasPermission` that the user attaches to a field; the
        # adapter has no such surface.
        public_names = [n for n in dir(adapter) if not n.startswith("_")]
        # PermissionDenied is OK; everything else must not contain these
        # substrings as a class-like name.
        for name in public_names:
            if name == "PermissionDenied":
                continue
            for forbidden in forbidden_substrings:
                assert_that(forbidden in name).described_as(
                    f"name {name!r} contains forbidden substring {forbidden!r}"
                ).is_false()
