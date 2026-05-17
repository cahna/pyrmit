"""Smoke + behavioural test: the runnable SQLAlchemy example.

Runs the example as a subprocess and asserts the expected per-actor
visible-titles lines appear in stdout.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assertpy import assert_that

_ROOT = Path(__file__).parent.parent.parent.parent
_EXAMPLE = _ROOT / "examples" / "sqlalchemy" / "example.py"


class TestSqlalchemyExampleRuns:
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
        # Admin sees all 4 titles; owner sees published + their own draft
        # (3 titles); stranger sees published + their own draft (3 titles
        # too, but a different mix that excludes the owner's draft).
        assert_that(result.stdout).contains("[admin]")
        assert_that(result.stdout).contains("[owner]")
        assert_that(result.stdout).contains("[stranger]")
        # The owner's draft must appear for admin and owner, NOT stranger.
        admin_line = next(line for line in result.stdout.splitlines() if "[admin]" in line)
        stranger_line = next(line for line in result.stdout.splitlines() if "[stranger]" in line)
        assert_that(admin_line).contains("Draft post")
        assert_that(stranger_line).does_not_contain("Draft post")
