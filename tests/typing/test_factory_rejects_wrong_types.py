"""Subprocess-driven mypy test: PolicyGuardFactory.guard rejects wrong types.

Making ``PolicyGuardFactory`` generic over ``(PrincipalT, ActionT,
SubjectT)`` is only meaningful if the host application's type checker
actually rejects misuse. This test locks two properties in:

  * ``guard(action=...)`` must be checked against the factory's
    ``ActionT`` -- passing an unrelated enum fails.
  * ``guard(..., load_subject=...)`` must be checked against the ``ST``
    pinned by ``subject_type`` -- a loader whose element type mismatches
    fails.

Three fixtures live in ``tests/typing/fixtures/``:

  - ``factory_right_types.py`` -- action + subject match; MUST pass.
  - ``factory_wrong_action.py`` -- wrong action enum; MUST fail arg-type.
  - ``factory_wrong_subject.py`` -- wrong loader element type; MUST fail
    arg-type.

Each is run through mypy as a subprocess in ``--strict`` mode with the
project's pyproject.toml config. ``--no-incremental`` avoids cache flake.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assertpy import assert_that

_HERE = Path(__file__).parent
_FIXTURES = _HERE / "fixtures"
_RIGHT = _FIXTURES / "factory_right_types.py"
_WRONG_ACTION = _FIXTURES / "factory_wrong_action.py"
_WRONG_SUBJECT = _FIXTURES / "factory_wrong_subject.py"


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


class TestFactoryRejectsWrongTypes:
    def test_right_types_typecheck_cleanly(self) -> None:
        """Positive control: matching action + subject types MUST type-check.

        If this fails, the negative tests below could pass spuriously
        (mypy failing on imports rather than on the type mismatch).
        """
        result = _run_mypy(_RIGHT)
        assert_that(result.returncode).described_as(
            f"factory_right_types.py must type-check. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_equal_to(0)

    def test_wrong_action_is_rejected_by_mypy(self) -> None:
        """Negative case: guard(action=...) must match the factory's ActionT."""
        result = _run_mypy(_WRONG_ACTION)
        assert_that(result.returncode).described_as(
            f"factory_wrong_action.py must NOT type-check. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_not_equal_to(0)
        combined = result.stdout + result.stderr
        assert_that(combined).contains("arg-type")

    def test_wrong_subject_loader_is_rejected_by_mypy(self) -> None:
        """Negative case: load_subject element type must match subject_type's ST."""
        result = _run_mypy(_WRONG_SUBJECT)
        assert_that(result.returncode).described_as(
            f"factory_wrong_subject.py must NOT type-check. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_not_equal_to(0)
        combined = result.stdout + result.stderr
        assert_that(combined).contains("arg-type")
