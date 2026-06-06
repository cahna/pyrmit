"""Smoke test: the runnable Strawberry example exits cleanly and prints expected output.

Subprocess form matches user experience (no module-import side effects) and
catches regressions where the example silently fails or its output drifts
from documented expectations.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from assertpy import assert_that

_ROOT = Path(__file__).parent.parent.parent.parent
_EXAMPLE = _ROOT / "examples" / "strawberry_graphql" / "example.py"


class TestStrawberryExampleRuns:
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
        # Admin and owner read the draft; stranger is denied via NOT_FOUND.
        assert_that(result.stdout).contains("[admin]")
        assert_that(result.stdout).contains("'title': 'Draft post'")
        assert_that(result.stdout).contains("[owner]")
        assert_that(result.stdout).contains("[stranger]")
        assert_that(result.stdout).contains("article_unpublished")

    def test_example_redacts_email_via_null_surface(self) -> None:
        result = subprocess.run(
            [sys.executable, str(_EXAMPLE)],
            capture_output=True,
            text=True,
            check=False,
            cwd=_ROOT,
        )
        lines = result.stdout.splitlines()
        # First scenario block is the published article: visible to all
        # three actors, but the NULL-surface contact guard redacts email
        # for the stranger -- silently, with no GraphQL error.
        published = {
            label: next(line for line in lines if line.startswith(f"[{label}]"))
            for label in ("admin", "owner", "stranger")
        }
        assert_that(published["admin"]).contains("'email': 'ada@example.com'")
        assert_that(published["owner"]).contains("'email': 'ada@example.com'")
        assert_that(published["stranger"]).contains("'email': None")
        assert_that(published["stranger"]).contains("errors=None")
