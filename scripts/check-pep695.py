#!/usr/bin/env python3
"""PEP 695 generic-syntax checker.

Scans the given Python files for legacy generic-typing anti-patterns and exits
non-zero on any match. Honors inline `# pep695-exempt: <reason>` annotations on
the same line or the immediately preceding line.

Detected anti-patterns (via the `ast` module):
    1. `from typing import TypeVar | ParamSpec | TypeAlias`
       (and the equivalent `from typing_extensions import ...`)
    2. `class Foo(Generic[T]):`  (PEP 484 inheritance form)
    3. `X: TypeAlias = ...`      (PEP 613 annotation form)

Permitted:
    - Any line / declaration annotated with `# pep695-exempt: <reason>`.
    - Use of `typing.Self`.
    - Files outside the configured project-authored scope (the caller controls
      this via argv; vendored / generated code is the caller's responsibility).

Usage:
    python scripts/check-pep695.py PATH [PATH ...]

Output (stderr, on violation):
    <path>:<line>:<col>: <forbidden pattern>; use PEP 695 syntax
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

# Names that, when imported from `typing` or `typing_extensions`, indicate
# legacy generic-typing usage that PEP 695 supersedes.
FORBIDDEN_TYPING_IMPORTS: frozenset[str] = frozenset({
    "TypeVar",
    "ParamSpec",
    "TypeAlias",
    "TypeVarTuple",
})

# Comment substring that exempts a line (and the next line below it) from the
# check. Reviewers MUST verify the carve-out is genuine (e.g. mirroring an
# upstream library that uses the legacy form).
EXEMPT_MARKER: str = "pep695-exempt:"


def _line_is_exempt(source_lines: list[str], lineno: int) -> bool:
    """Return True if the violation at `lineno` (1-indexed) is exempted.

    A violation is exempt if either the line itself or the immediately
    preceding line carries the `# pep695-exempt:` marker.
    """
    if 1 <= lineno <= len(source_lines):
        if EXEMPT_MARKER in source_lines[lineno - 1]:
            return True
    if 2 <= lineno <= len(source_lines) + 1:
        if EXEMPT_MARKER in source_lines[lineno - 2]:
            return True
    return False


def _scan_imports(
    node: ast.ImportFrom,
    source_lines: list[str],
) -> list[tuple[int, int, str]]:
    """Detect forbidden `from typing import …` patterns."""
    if node.module not in {"typing", "typing_extensions"}:
        return []
    violations: list[tuple[int, int, str]] = []
    for alias in node.names:
        if alias.name not in FORBIDDEN_TYPING_IMPORTS:
            continue
        if _line_is_exempt(source_lines, node.lineno):
            continue
        violations.append((
            node.lineno,
            node.col_offset + 1,
            f"forbidden import: `{alias.name}` from `{node.module}`; use PEP 695 syntax",
        ))
    return violations


def _scan_class_bases(
    node: ast.ClassDef,
    source_lines: list[str],
) -> list[tuple[int, int, str]]:
    """Detect forbidden `class Foo(Generic[T]):` base."""
    violations: list[tuple[int, int, str]] = []
    for base in node.bases:
        if not isinstance(base, ast.Subscript):
            continue
        value = base.value
        if not isinstance(value, ast.Name):
            continue
        if value.id != "Generic":
            continue
        if _line_is_exempt(source_lines, base.lineno):
            continue
        violations.append((
            base.lineno,
            base.col_offset + 1,
            (f"forbidden `Generic[...]` base on class `{node.name}`; use `class {node.name}[T]:` syntax"),
        ))
    return violations


def _scan_annotation(
    node: ast.AnnAssign,
    source_lines: list[str],
) -> list[tuple[int, int, str]]:
    """Detect forbidden `X: TypeAlias = ...` annotations."""
    ann = node.annotation
    is_type_alias = (isinstance(ann, ast.Name) and ann.id == "TypeAlias") or (
        isinstance(ann, ast.Attribute) and ann.attr == "TypeAlias"
    )
    if not is_type_alias:
        return []
    if _line_is_exempt(source_lines, node.lineno):
        return []
    return [
        (
            ann.lineno,
            ann.col_offset + 1,
            "forbidden `: TypeAlias` annotation; use `type Name[T] = ...` syntax",
        )
    ]


def scan_file(path: Path) -> list[tuple[int, int, str]]:
    """Scan `path` and return a list of (line, column, message) violations.

    Lines and columns are 1-indexed. Files that aren't valid Python source are
    skipped silently (binary, non-UTF-8, or syntactically broken).
    """
    try:
        source = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []
    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    source_lines = source.splitlines()
    violations: list[tuple[int, int, str]] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            violations.extend(_scan_imports(node, source_lines))
        elif isinstance(node, ast.ClassDef):
            violations.extend(_scan_class_bases(node, source_lines))
        elif isinstance(node, ast.AnnAssign):
            violations.extend(_scan_annotation(node, source_lines))
    return violations


def main(argv: list[str]) -> int:
    """Entry point. Returns the process exit code."""
    if len(argv) < 2:
        print(
            "usage: check-pep695.py PATH [PATH ...]",
            file=sys.stderr,
        )
        return 2

    total = 0
    for raw in argv[1:]:
        path = Path(raw)
        if not path.is_file() or path.suffix != ".py":
            continue
        for line, col, msg in scan_file(path):
            print(f"{path}:{line}:{col}: {msg}", file=sys.stderr)
            total += 1

    if total:
        print(
            f"\ncheck-pep695: {total} violation(s) found. ",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
