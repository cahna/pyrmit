#!/usr/bin/env python3
"""No ``# type: ignore`` / ``# pyright: ignore`` checker.

Library code MUST NOT suppress the type checker; use ``typing.cast`` with
an explanatory comment instead. The escape hatch exists because type
suppression silently hides regressions, whereas a ``cast`` is a single
documented assertion the next reader can audit.

This script uses the ``tokenize`` module so the marker is detected only
inside real source comments -- ``# type: ignore`` mentioned in a
docstring, string literal, or markdown example is NOT a violation. Comments
inside f-string expressions are likewise tokenised correctly.

The pre-commit hook scopes this to ``^src/`` only; tests and examples are
free to use narrow ``# type: ignore[...]`` casts where the type system
cannot be persuaded (e.g. asserting frozen-dataclass immutability raises).

Usage:
    python scripts/check-no-type-ignore.py PATH [PATH ...]

Output (stderr, on violation):
    <path>:<line>:<col>: <message>
"""

from __future__ import annotations

import io
import re
import sys
import tokenize
from pathlib import Path

# Matches `# type: ignore`, `# type:ignore`, `# pyright: ignore`,
# `# pyright:ignore`, with optional `[code]` bracket suffix. Case-sensitive
# to match what mypy / pyright actually recognise.
_MARKER_RE: re.Pattern[str] = re.compile(r"#\s*(type|pyright)\s*:\s*ignore\b")


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Return (line, col, message) violations for ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    violations: list[tuple[int, int, str]] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for tok in tokens:
            if tok.type != tokenize.COMMENT:
                continue
            match = _MARKER_RE.search(tok.string)
            if match is None:
                continue
            lineno, col = tok.start
            # Re-anchor column to the marker, not the start of the
            # comment, so the reported position points at the offending
            # text rather than the leading ``#``.
            col += match.start()
            tool = match.group(1)
            message = (
                f"forbidden `# {tool}: ignore` in library code; "
                f"use `typing.cast(...)` with an explanatory comment instead"
            )
            violations.append((lineno, col + 1, message))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return []
    return violations


def main(argv: list[str]) -> int:
    """Entry point. Returns the process exit code."""
    if len(argv) < 2:
        print("usage: check-no-type-ignore.py PATH [PATH ...]", file=sys.stderr)
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
            f"\ncheck-no-type-ignore: {total} violation(s) found.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
