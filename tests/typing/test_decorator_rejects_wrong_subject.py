"""Subprocess-driven mypy test: engine.policy decorator must reject mismatched subjects.

This is a critical typing property of the engine: a policy registered
for ``MatchSubject`` whose function actually takes ``ClubSubject`` MUST
fail strict type checking. Without this test, a future refactor that
silently widens the decorator's ST binding would pass review but break the
typed-engine guarantee.

Two control fixtures live in ``tests/typing/fixtures/``:

  - ``right_subject_policy.py`` -- types match; MUST pass.
  - ``wrong_subject_policy.py`` -- types mismatch; MUST fail with arg-type.

We run mypy as a subprocess against each in ``--strict`` mode with the
project's pyproject.toml config. ``--no-incremental`` avoids cache flake
across runs.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assertpy import assert_that

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures"
_RIGHT = _FIXTURES / "right_subject_policy.py"
_WRONG = _FIXTURES / "wrong_subject_policy.py"


def _run_mypy(target: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            "--strict",
            "--no-incremental",
            "--config-file",
            str(_HERE.parent.parent / "pyproject.toml"),
            str(target),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


class TestDecoratorRejectsWrongSubject:
    def test_right_subject_policy_typechecks_cleanly(self) -> None:
        """Positive control: this fixture MUST type-check.

        If this fails, the negative test below would pass spuriously
        (mypy could be failing on imports rather than the policy mismatch).
        """
        result = _run_mypy(_RIGHT)
        assert_that(result.returncode).described_as(
            f"right_subject_policy.py must type-check. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_equal_to(0)

    def test_wrong_subject_policy_is_rejected_by_mypy(self) -> None:
        """Negative case: decorator subject_type vs function subject must match."""
        result = _run_mypy(_WRONG)
        assert_that(result.returncode).described_as(
            f"wrong_subject_policy.py must NOT type-check. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_not_equal_to(0)
        # mypy emits an arg-type error when the decorated function's signature
        # doesn't match the inferred ST from subject_type=MatchSubject.
        combined = result.stdout + result.stderr
        assert_that(combined).contains("arg-type")
