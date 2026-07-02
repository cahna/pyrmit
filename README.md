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
  ALLOW decisions are actually covered). A crashing policy is also
  logged at WARNING (with `exc_info=True`) on the `pyrmit.core.engine`
  logger, since `engine.decide`/`engine.adecide` treat it as noteworthy
  even though the caller sees a normal deny `Decision`.
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
  authorization decision, and the same guard blocks attachment to
  `@strawberry.subscription` fields for the same reason — a subscription
  resolver produces the stream before any decision can be reached, so a
  post-resolution guard can't gate it. Pre-resolution guards (the
  `load_subject` / `load_subject_from_source` phases of `policy_guard`)
  work on subscriptions: the decision is made before the stream starts,
  so a deny raises (or nulls) instead of ever opening the subscription.
  `PolicyGuardFactory(engine=..., principal_loader=...)` is the
  recommended entry point for real schemas — it captures the engine and
  principal loader once and exposes `.guard(...)` / `.post_resolution_guard(...)`
  so individual fields don't restate the cross-cutting deps. The factory
  is generic — `PolicyGuardFactory[PrincipalT, ActionT, SubjectT]` — and
  its type parameters are normally inferred from the `engine` and
  `principal_loader` arguments, so a factory built from a
  `PolicyEngine[Principal[Actor], Action, Article]` propagates those
  types onto every `.guard(...)` call: mypy rejects a wrong `action`
  enum value or a subject loader whose element type doesn't match
  `subject_type`. See `examples/strawberry_graphql/example_di.py` for a
  DI-style wiring.
  - **`deny_handler`**: `policy_guard`, `post_resolution_policy_guard`,
    and `PolicyGuardFactory` all accept an optional `deny_handler:
    (Decision, DenialSurface) -> Exception` hook, called for FORBIDDEN
    and NOT_FOUND denials (NULL never raises, so it's never called for
    that surface). Use it to raise a host application's own exception
    taxonomy — e.g. one carrying a structured error code for GraphQL
    clients — instead of pyrmit's built-in `PermissionDenied` /
    `ResourceNotFound`, which are plain `Exception` subclasses and do
    **not** carry an `extensions.code`. The default,
    `default_deny_handler`, preserves that historical behavior. On the
    factory, `deny_handler` is set once and applied to every guard it
    builds, with a per-call override on `.guard(...)` /
    `.post_resolution_guard(...)`.
  - **`denial_surface`**: `guard()`, `post_resolution_guard()`, and the
    bare `policy_guard()` / `post_resolution_policy_guard()` functions
    all accept an optional `denial_surface: DenialSurface` override.
    It applies only to that one field attachment — the binding's own
    registered surface, and any other guard built against the same
    binding, is unaffected.
  - The per-request principal cache is keyed by `(info.context,
    principal_loader)` identity, not just by context: two guards on the
    same request built from factories with *different* principal
    loaders never share a cached principal, even though they share the
    same context object.
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
