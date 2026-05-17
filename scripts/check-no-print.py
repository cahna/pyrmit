#!/usr/bin/env python3
"""No-print + no-logging.basicConfig checker.

Library code MUST NOT call ``print(...)`` (always-on console I/O is hostile
to embedding hosts) and MUST NOT call ``logging.basicConfig(...)`` (it
mutates the host application's root logger). Both are forbidden in
``src/`` and ``tests/`` per the library-grade observability rule.

Scans the given Python files via the ``ast`` module so that mentions of
either name inside comments, docstrings, or string literals are not
false-positives. Only real call sites fire.

Usage:
    python scripts/check-no-print.py PATH [PATH ...]

Output (stderr, on violation):
    <path>:<line>:<col>: forbidden call to <name>
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path


def _is_print_call(node: ast.Call) -> bool:
    """Return True if ``node`` is a call to the builtin ``print``.

    Matches the bare ``print(...)`` name; deliberately does NOT match
    method calls like ``writer.print(...)`` (which use ``print`` as an
    attribute name, not the builtin).
    """
    return isinstance(node.func, ast.Name) and node.func.id == "print"


def _is_logging_basicconfig_call(node: ast.Call) -> bool:
    """Return True if ``node`` is a call to ``logging.basicConfig(...)``.

    Matches the canonical ``logging.basicConfig(...)`` attribute-access
    form. Aliased imports (``from logging import basicConfig`` then
    ``basicConfig(...)``) are also caught via the bare-name branch.
    """
    func = node.func
    if isinstance(func, ast.Attribute):
        if func.attr != "basicConfig":
            return False
        value = func.value
        return isinstance(value, ast.Name) and value.id == "logging"
    if isinstance(func, ast.Name):
        return func.id == "basicConfig"
    return False


def _scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Return (line, col, message) violations for ``path``."""
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    violations: list[tuple[int, int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _is_print_call(node):
            violations.append((
                node.lineno,
                node.col_offset + 1,
                "forbidden call to `print(...)`; use the `pyrmit` logger or test fixtures",
            ))
            continue
        if _is_logging_basicconfig_call(node):
            violations.append((
                node.lineno,
                node.col_offset + 1,
                "forbidden call to `logging.basicConfig(...)`; library code MUST NOT mutate the host logging stack",
            ))
    return violations


def main(argv: list[str]) -> int:
    """Entry point. Returns the process exit code."""
    if len(argv) < 2:
        print("usage: check-no-print.py PATH [PATH ...]", file=sys.stderr)
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
            f"\ncheck-no-print: {total} violation(s) found.",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
