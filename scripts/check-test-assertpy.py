#!/usr/bin/env python3
"""assertpy test-discipline checker.

For each test file passed on argv, verify both:

1.  The file imports ``assertpy`` (positive check). A test file that does not
    import ``assertpy`` cannot be using ``assert_that(...)`` and is therefore a
    violation.
2.  No bare ``assert`` statement appears in a test body unless the same line
    (or the immediately preceding line) carries an inline ``# narrow:`` comment
    documenting that the bare ``assert`` exists only to help mypy narrow a type
    after a prior ``assert_that(...)`` already established the invariant.

Test fixture and ``conftest.py`` files are excluded by the pre-commit hook's
``exclude`` regex, not by this script.

Usage:
    python scripts/check-test-assertpy.py PATH [PATH ...]
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

NARROW_MARKER = "# narrow:"


def _scan_file(path: Path) -> list[tuple[int, int, str]]:  # noqa: C901
    """Return (line, col, message) violations for `path`."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[tuple[int, int, str]] = []
    imports_assertpy = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "assertpy":
            imports_assertpy = True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "assertpy":
                    imports_assertpy = True

    if not imports_assertpy:
        violations.append((
            1,
            1,
            "test file does not import `assertpy`; use of `assert_that(...)` is required in tests",
        ))

    source_lines = source.splitlines()
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        lineno = node.lineno
        line = source_lines[lineno - 1] if 0 < lineno <= len(source_lines) else ""
        prev = source_lines[lineno - 2] if 1 < lineno <= len(source_lines) + 1 else ""
        if NARROW_MARKER in line or NARROW_MARKER in prev:
            continue
        violations.append((
            lineno,
            node.col_offset + 1,
            "bare `assert` in test body; use assertpy or annotate with `# narrow:`",
        ))
    return violations


def main(argv: list[str]) -> int:
    """Entry point."""
    if len(argv) < 2:
        print("usage: check-test-assertpy.py PATH [PATH ...]", file=sys.stderr)
        return 2

    total = 0
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file() or path.suffix != ".py":
            continue
        for line, col, msg in _scan_file(path):
            print(f"{path}:{line}:{col}: {msg}", file=sys.stderr)
            total += 1
    if total:
        print(
            f"\ncheck-test-assertpy: {total} violation(s) found.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
