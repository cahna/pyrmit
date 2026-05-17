# pyrmit

[![ci](https://github.com/cahna/pyrmit/actions/workflows/ci.yml/badge.svg)](https://github.com/cahna/pyrmit/actions/workflows/ci.yml)
[![PyPI version](https://img.shields.io/pypi/v/pyrmit.svg)](https://pypi.org/project/pyrmit/)
[![Python versions](https://img.shields.io/pypi/pyversions/pyrmit.svg)](https://pypi.org/project/pyrmit/)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

> Status: **v0.x — experimental**. API may change without notice.

A typed, fail-closed authorization engine for Python 3.12+. Strongly-typed
generic policies, two-state decisions, and pluggable audit and entitlement
providers. Optional adapters for Strawberry GraphQL, FastAPI, and
SQLAlchemy.

## Install

```bash
pip install pyrmit                                       # core only
pip install "pyrmit[strawberry,fastapi,sqlalchemy]"      # with adapters
```

The adapter extras pull in their respective frameworks; install only the
ones you use.

## Quickstart

```python
from dataclasses import dataclass
from enum import StrEnum

from pyrmit import ALLOW, Decision, Entitlements, PolicyEngine, Principal, deny


class Action(StrEnum):
    READ = "read"


@dataclass(frozen=True)
class Actor:
    user_id: int
    is_admin: bool


@dataclass(frozen=True)
class Article:
    id: int
    owner_id: int
    is_published: bool


engine: PolicyEngine[Principal[Actor], Action, Article] = PolicyEngine()


@engine.policy(action=Action.READ, subject_type=Article)
def can_read_article(principal: Principal[Actor], article: Article) -> Decision:
    if principal.actor.is_admin:
        return ALLOW
    if article.is_published:
        return ALLOW
    if article.owner_id == principal.actor.user_id:
        return ALLOW
    return deny("article_unpublished")


alice = Principal[Actor](
    actor=Actor(user_id=42, is_admin=False),
    entitlements=Entitlements.empty(),
)
hidden = Article(id=1, owner_id=99, is_published=False)
decision = engine.decide(principal=alice, action=Action.READ, subject=hidden)
assert decision.allowed is False
assert decision.reason == "article_unpublished"
```

This example is exercised verbatim by
[`tests/integration/typed_decisions/test_readme_quickstart.py`](tests/integration/typed_decisions/test_readme_quickstart.py)
to make sure the README never drifts from real behavior.

## Key properties

- **Two-state Decision** — `allowed: bool` plus a stable machine-readable
  `reason`. No third state.
- **Fail-closed** — missing policy denies (`policy_not_registered`); a
  policy raising any exception denies (`policy_error`); audit-store
  failure denies (`audit_unavailable`) when `audit_failure_mode="deny"`
  (which requires `audit_allows=True` at engine construction so that
  ALLOW decisions are actually covered).
- **Defensively immutable** — `Decision.detail` and `AuditEntry.metadata`
  are wrapped in `MappingProxyType` at construction and reject non-primitive
  values at runtime.
- **Strict typing** — `mypy --strict` clean, no `Any` in core, no
  `type: ignore`. The decorator's subject_type binding is enforced by
  the type checker (see the negative test under `tests/typing/`).

## Adapters

Adapters live under `pyrmit.adapters.*` and are optional extras:

- **Strawberry**: `policy_guard(...)` — single-extension field guard with
  pre-resolution / from-source / post-resolution loader phases. NULL
  denial short-circuits before the resolver runs.
  `post_resolution_policy_guard(...)` is the explicit, safer counterpart
  for redaction-style use; it refuses to run inside a mutation operation
  by default (`read_only=True`) because the resolver runs before the
  authorization decision.
  `PolicyGuardFactory(engine=..., principal_loader=...)` is the
  recommended entry point for real schemas — it captures the engine and
  principal loader once and exposes `.guard(...)` / `.post_resolution_guard(...)`
  so individual fields don't restate the cross-cutting deps. See
  `examples/strawberry_graphql/example_di.py` for a DI-style wiring.
- **FastAPI**: `require_policy(...)` — dependency factory that translates
  denials to HTTP responses; the NULL surface requires a `null_mapper`.
- **SQLAlchemy**: `visibility_scope(...)` decorator marks a function as
  the per-actor row-level visibility predicate for a model;
  `verify_scope_applied(...)` is a tripwire test helper that checks the
  predicate is genuinely present on a compiled query.

## Development

```bash
uv sync --all-extras
uv run pytest -q
uv run mypy src tests
uv run ruff check
uv run ruff format --check
```

See [CONTRIBUTING.md](CONTRIBUTING.md) for project conventions
(PEP 695 generics, `assertpy` in tests, no `Any` outside the documented
carve-outs, etc.) and [SECURITY.md](SECURITY.md) for the disclosure
policy.

## License

Apache-2.0. See [LICENSE](LICENSE).
