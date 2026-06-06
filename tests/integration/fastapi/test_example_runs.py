"""Smoke + behavioural test: the runnable FastAPI example.

Runs the example as a subprocess (matches the user experience) and
asserts the expected per-actor outcomes appear in stdout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assertpy import assert_that

_ROOT = Path(__file__).parent.parent.parent.parent
_EXAMPLE = _ROOT / "examples" / "fastapi" / "example.py"


class TestFastapiExampleRuns:
    def test_example_exits_cleanly(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_EXAMPLE)],
            capture_output=True,
            text=True,
            check=False,
            cwd=_ROOT,
        )
        assert_that(result.returncode).described_as(
            f"example must exit 0. stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        ).is_equal_to(0)

    def test_example_prints_expected_outcomes(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_EXAMPLE)],
            capture_output=True,
            text=True,
            check=False,
            cwd=_ROOT,
        )
        # Admin and owner read the unpublished draft (200); stranger is
        # denied with a 404 NOT_FOUND surface.
        assert_that(result.stdout).contains("[admin] status=200")
        assert_that(result.stdout).contains("[owner] status=200")
        assert_that(result.stdout).contains("[stranger] status=404")
        assert_that(result.stdout).contains("Draft post")
        assert_that(result.stdout).contains("NOT_FOUND")
