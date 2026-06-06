# Contributing to pyrmit

Thanks for your interest in contributing. `pyrmit` is a small,
type-strict authorization library; the bar for changes is "correct,
typed, tested, and consistent with the rest of the codebase."

## Development setup

```bash
git clone https://github.com/cahna/pyrmit
cd pyrmit
uv sync --all-extras
uv run pre-commit install
```

Requires Python 3.12 or 3.13 and [`uv`](https://docs.astral.sh/uv/).

## Quality gates

Before opening a pull request, ensure all four commands pass cleanly:

```bash
uv run pytest -q
uv run mypy src tests
uv run ruff check
uv run ruff format --check
```

`pre-commit run --all-files` runs an equivalent set plus a few
project-specific checks (see below).

## Project conventions

These rules are enforced by `pre-commit` hooks. The rationale for each
rule lives below; the configuration that enforces it lives in
`pyproject.toml` and `.pre-commit-config.yaml`.

- **Type everything.** `mypy --strict` is non-negotiable.
- **No `type: ignore` and no `# pyright: ignore`** in committed code.
  Use `typing.cast` as the escape hatch when the type system can't be
  convinced.
- **No `Any` outside the documented framework-adapter carve-outs.**
  `pyproject.toml` enumerates the exact modules that are allowed to
  surface `Any` (Strawberry / FastAPI / SQLAlchemy boundaries plus
  `pyrmit.core.lazy`).
- **PEP 695 generics only.** No `from typing import TypeVar | ParamSpec
  | TypeAlias` and no `class Foo(Generic[T]):`. The one exception is
  `Principal[A, E]`, which needs `typing_extensions.TypeVar` for the
  PEP 696 default until the project's minimum supported Python becomes
  3.13+; that file carries a `pep695-exempt:` annotation explaining
  the carve-out.
- **No emojis** in source code or commit messages.
- **Tests use `assertpy`,** not bare `assert` statements. The
  `scripts/check-test-assertpy.py` hook enforces this.
- **Conventional commits** via `uv run cz commit` (Commitizen). Tags
  follow PEP 440 via `cz bump`.

## Changes that need extra care

- **Anything affecting fail-closed semantics or audit integrity** is a
  security-sensitive change. Add an integration test under
  `tests/security/` that demonstrates the new invariant holds.
- **Adapter changes** (Strawberry / FastAPI / SQLAlchemy) must include
  a corresponding integration test under the matching
  `tests/integration/` subdirectory (`strawberry/`, `fastapi/`,
  `sqlalchemy/`).
- **Public API additions** must be re-exported from the relevant
  `__init__.py` and added to its `__all__`.

## Reporting bugs

For non-security bugs, please open an issue at
<https://github.com/cahna/pyrmit/issues>. For security-sensitive
reports, see [SECURITY.md](SECURITY.md).
