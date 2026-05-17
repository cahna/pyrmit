<!--
Sync Impact Report
==================
Version change: 2.0.0 -> 2.1.2
Bump rationale: cumulative. MINOR for the introduction of Principle VII
(Methodology-Agnostic Published Artifacts) and its enforcement subsection.
PATCH on top of that to clarify the enforcement mechanism: enforcement is
primarily code-review-driven with a documented contributor-facing grep
recipe rather than a required CI gate (the cost of a generous-by-design
grep failing on legitimate prose was judged higher than the marginal value
over reviewer attention). The token set was also widened to cover SC-NNN,
T-NNN, and research R-N references, and a narrow path-pattern carve-out
was added for tooling-configuration files. A second PATCH (2.1.2) widened
the token set again after a cleanup pass found leaks the recipe missed:
spec-section citations ("spec §N.N", "spec.md", "the spec"), design-artifact
filenames (data-model.md, contracts/*.md, plan.md, tasks.md, research.md,
quickstart.md), user-story identifiers ("User Story N", "Story N", "USn"),
spec-defined pattern names ("Pattern A"/"Pattern B" used without their
self-describing equivalents), and letter-suffixed task IDs (T063b). No
prior principle is redefined or removed; Principles I-VI retain their
numbering and semantics.

Modified principles:
- (none renamed or redefined)

Added sections:
- Principle VII: Methodology-Agnostic Published Artifacts
- Quality & Tooling Standards subsection: "Methodology References in
  Published Artifacts" (enforcement detail for Principle VII)
- Review Gates: new bullet enforcing Principle VII at PR merge time

Removed sections:
- (none)

Templates requiring updates:
- .specify/templates/plan-template.md: OK -- the existing "Constitution Check"
  section is generic ("Gates determined based on constitution file") and
  remains valid without edit; new principle is picked up automatically.
- .specify/templates/spec-template.md: OK -- no principle-specific scaffolding
  needs changing.
- .specify/templates/tasks-template.md: OK -- no new task category is implied
  beyond cleanup tasks that get logged per-feature.
- .specify/templates/checklist-template.md: OK -- generic.
- README.md (repository root for pyrmit): OK -- grep confirmed no methodology
  tokens currently leak there.

Follow-up TODOs (NOT part of this amendment; logged for a separate cleanup PR):
- src/pyrmit/__init__.py: docstring and inline comment reference
  "constitution Principle V" (lines ~9, ~61). Restate in domain terms.
- src/pyrmit/audit/logging.py: docstring references "constitution Principle V"
  (line ~13). Restate in domain terms.
- src/pyrmit/core/engine.py: docstrings reference "constitution Principle II",
  the v1.3.0 amendment, and a specs/ path (lines ~4-6). Remove specs/ link;
  restate typing rule in domain terms.
- src/pyrmit/core/errors.py: docstring references "constitution Principle III"
  and "carve-out the constitution explicitly allows" (lines ~1, ~5).
- src/pyrmit/core/audit.py: docstrings reference "constitution Principle III"
  and "v1.0.1" amendment (lines ~8, ~94).
- src/pyrmit/core/lazy.py: comment references "the framework-boundary Any
  surfaces that the constitution carves out" (line ~27).
- src/pyrmit/adapters/fastapi/dependency.py: docstring references "the
  constitution's 'fail closed' default" (line ~93). "Fail closed" can stay;
  the phrase "the constitution's" must go.
- src/pyrmit/adapters/strawberry/guard.py: docstrings reference "constitution
  FR-024 / FR-046" and "constitution Principle VII -- fail loudly on
  misconfiguration" (lines ~5, ~221-223). The "Principle VII" reference is
  also stale (the constitution had only I-VI before this amendment) and is
  unrelated to the new Principle VII; restate in domain terms.
- tests/unit/core/test_logging_setup.py: module docstring names a task ID
  ("T016") and "constitution Principle V" (line ~1). Restate in behavioral
  terms.
- CONTRIBUTING.md: line 35 links to ".specify/memory/constitution.md" as the
  rationale source. Because CONTRIBUTING.md ships in the sdist (per
  pyproject.toml), this reference leaks methodology to the published package.
  Either (a) remove the reference and restate the rules locally, or (b) drop
  CONTRIBUTING.md from the sdist include list. Choice deferred to the cleanup
  PR.

All FOLLOW-UP items above are tracked here so the cleanup PR has a single
authoritative checklist. The amendment PR itself only modifies this
constitution file.
-->

# Pyrmit Constitution

## Core Principles

### I. Test-First Development (NON-NEGOTIABLE)

Test-Driven Development is mandatory wherever it is technically feasible. The Red-Green-Refactor
cycle MUST be followed: a failing test is written and reviewed before any production code that
makes it pass. Pull requests that introduce or modify behavior MUST include tests authored before
(or alongside, when strictly necessary) the implementation.

- Every public function, class, and policy decision point MUST have direct unit-test coverage.
- Integration tests MUST exist for any contract that crosses a module boundary or persists state.
- Code paths that cannot be tested deterministically (e.g., true randomness, network races) MUST
  be isolated behind seams that ARE tested with fakes or fixtures.

**Rationale**: As an authorization library, undetected regressions can become security
incidents. TDD enforces that every behavior is specified, observable, and regression-protected
by design.

### II. Strict Static Typing

The library MUST type-check cleanly under strict `mypy` settings. Type safety is a security
property, not a stylistic preference.

- The `Any` type is FORBIDDEN in library source. Use `typing.cast()`, `TypeVar`s, `Protocol`s,
  or precise generics instead.
- `# type: ignore`, `# pyright: ignore`, and equivalent suppression comments are FORBIDDEN.
  If the type system cannot express a constraint, refactor or use `typing.cast()` with a
  comment explaining the invariant being asserted.
- `mypy` MUST be configured in strict mode and MUST pass with zero errors in CI on every
  pull request. Loosening `mypy` configuration is a constitution amendment, not a code change.
- **`pyright` MUST NOT be used as a type-check gate** in CI, in pre-commit, or in any
  enforcement context. mypy is the sole type-check gate for this project. Rationale below
  under the "Single type checker" subsection.
- Public APIs MUST be fully annotated; no implicit `Any` at module boundaries.
- All functions and methods — public **and** private — MUST carry explicit type annotations
  on every parameter and on the return type. `mypy --strict`'s `disallow_untyped_defs` MUST
  remain enabled. An unannotated def is treated as a CI failure, not a stylistic suggestion.
- All generic type parameterization MUST use **PEP 695 syntax** (Python 3.12+). See the
  "PEP 695 Generic Syntax" subsection under Quality & Tooling Standards for the canonical
  forms, the narrowly-scoped carve-outs, and the enforcement mechanism.

**Rationale**: Authorization decisions hinge on subtle invariants (subject identity, resource
ownership, scope membership). Strict typing makes those invariants machine-checked and
prevents whole classes of permission-bypass bugs.

#### Single type checker (clarification, v1.4.0)

mypy is the project's sole strict type-check gate. `pyright`, `pyre`, `pytype`, and any
other competing type checker MUST NOT be added as a CI gate, pre-commit hook, IDE-required
checker, or any other enforcement mechanism. Developers MAY run them locally as
diagnostic tools, but a `pyright`/`pyre`/`pytype` diagnostic NEVER blocks a commit, a PR,
or a release.

The prohibition exists because pyright actively rejects valid PEP 695 nested generic
constraint syntax (`def m[ST: SubjectT](...)`) that the project's own typing patterns
(spec §12.6 Pattern A union, Pattern B marker base class) require. Adding pyright as a
second gate forces a choice between (a) the spec's documented user-facing typing
patterns, or (b) the dual-checker mandate. The project chooses (a). If `pyright` later
matches mypy on PEP 695 constraint semantics, this rule can be revisited via a separate
constitution amendment.

The suppression comments `# type: ignore`, `# pyright: ignore`, and `# pyre-ignore`
remain forbidden in source per the bullets above. They are forbidden as suppression
markers regardless of which type checker is invoked; banning them is a hygiene rule, not
a checker-selection rule.

### III. Test Assertion Discipline (assertpy)

Tests MUST use `assertpy` for behavioral assertions. Bare `assert` statements are FORBIDDEN
in test bodies except in the narrow case where one is required to help `mypy` narrow a
type after a value has already been asserted by `assertpy` — and that exception MUST be
accompanied by a one-line comment naming the narrowing intent.

- Every assertion MUST be expressed via `assert_that(...)`, exercising `assertpy`'s
  fluent matchers for clearer failure messages and richer diagnostic output.
- Tests MUST NOT rely on Python's `assert` for primary verification, because `-O` strips
  asserts and obscures intent.
- Custom matchers SHOULD be added (via `assertpy` extensions) when the same assertion
  pattern repeats more than twice.

**Rationale**: Authorization tests routinely check structured policy evaluations; rich,
self-describing assertions make test failures diagnostic rather than cryptic, and they
survive `-O` and similar optimizations.

### IV. Library-Grade Observability

Logging MUST follow Python's library logging guidelines (PEP 282 and the official
`logging` HOWTO for libraries). The library MUST NOT impose logging configuration on
its consumers.

- Each module MUST obtain its logger via `logging.getLogger(__name__)`.
- The package's top-level logger MUST attach a `logging.NullHandler()` and MUST NOT add
  any other handler, set any level, or call `logging.basicConfig()`.
- Log messages MUST use deferred (`%`-style) formatting via the `logger` API
  (e.g., `logger.info("denied subject=%s", subject_id)`) — never pre-formatted f-strings,
  which defeat sampling and structured-log adapters.
- Authorization decisions (allow/deny) MUST be logged at `INFO` with sufficient structured
  context (subject id, action, resource id, policy name, decision) to support audit;
  internal traces use `DEBUG`. Sensitive material (tokens, secrets, raw credentials)
  MUST NEVER be logged at any level.
- The library MUST NOT log to stdout/stderr directly; only via the `logging` module.

**Rationale**: As an embedded library, Pyrmit cannot dictate the host application's
logging stack. Following PEP 282 keeps the library a good citizen and ensures audit-grade
authorization logs remain available to consumers without breaking their pipelines.

### V. Documentation as Contract

`README.md` is the canonical, user-facing contract for the library. It MUST be accurate,
detailed, and synchronized with every shipped behavior.

- Any pull request that adds, removes, or alters a public API, policy syntax, configuration
  option, or supported integration MUST include the corresponding `README.md` update in the
  same PR. Documentation drift is a defect.
- `README.md` MUST cover: installation, a runnable quickstart, the full public API surface
  with examples, configuration options, security model & threat assumptions, logging
  guidance, and a versioning/compatibility statement.
- Code examples in `README.md` MUST be executed in CI (e.g., via doctest, `pytest --doctest-glob`,
  or a dedicated example test) to guarantee they remain correct.
- `markdownlint-cli2` MUST pass on all Markdown in the repository, **excepting files under
  `specs/`**. Specification documents are working drafts written under tight feedback loops with
  AI tooling; subjecting them to the publish-grade lint gate produces noise that obscures real
  documentation defects in `README.md`, `docs/`, and example READMEs. The exception MUST be
  encoded in `.markdownlint-cli2.yaml` (e.g., `ignores: ["specs/**"]`) so the gate cannot
  silently regress to checking specs.

**Rationale**: Authorization libraries are adopted on the basis of trust. Out-of-date
documentation creates misuse, and misuse of an authz library is a security incident.

### VI. Security-First Design

Security is a primary acceptance criterion at every stage — design, implementation,
review, and testing — not a polishing pass.

- Every design document and feature spec MUST include an explicit "Security Considerations"
  section enumerating: trust boundaries, attacker model assumptions, fail-closed defaults,
  input validation requirements, and any sensitive data handled.
- The library MUST fail closed: when policy evaluation cannot complete, the result MUST
  carry "deny" semantics. Ambiguous outcomes MUST NEVER be coerced into "allow".
- All external inputs (policies, subject/resource attributes, identifiers) MUST be validated
  at the trust boundary, with rejection surfaced as an explicit, typed outcome.
- Test suites MUST include adversarial cases: privilege escalation attempts, policy
  injection, identifier confusion (UUID parsing, type confusion), and serialization edge
  cases — proportional to the surface being changed.
- Dependencies MUST be vetted: new runtime dependencies require explicit justification in
  the PR and a review of their maintenance posture and known CVE history. See the
  "Runtime Dependency Policy" subsection under Quality & Tooling Standards for the
  default-deny stance on runtime dependencies.
- Secret material MUST NEVER appear in logs, error messages, exception strings, test
  fixtures committed to the repository, or example documentation.

**Rationale**: Pyrmit makes deny/allow decisions; a flaw in this library is a flaw in
every consumer's security posture. Security review must be continuous, not deferred.

### VII. Methodology-Agnostic Published Artifacts

The library's published surface — every file shipped in the PyPI sdist or wheel, plus every
public-facing document in the repository — MUST remain methodology-agnostic. End users
install `pyrmit` to obtain a typed, fail-closed authorization library; they do not need to
know which planning framework, specification system, or agent-assisted workflow the
maintainers use internally. The internal development methodology MUST NOT leak into the
artifacts users see.

- **Source code under `src/`** (docstrings, comments, module headers, error messages, log
  format strings, exception messages) MUST NOT reference `speckit`, `.specify/`, "the
  constitution", constitution principles (by number, by name, or by paraphrase such as
  "constitution carve-out"), files or paths under `specs/`, task IDs from the
  speckit-generated `tasks.md` (e.g. `T016`), functional-requirement identifiers from
  speckit specs (e.g. `FR-024`), amendment version numbers (e.g. "v1.3.0 amendment"),
  agent-assisted workflows, or any other internal development methodology artifact. Where
  a rationale needs to live next to the code, restate the rule in domain terms — e.g.
  "fail closed when subject resolution fails" — rather than citing the governance
  document that motivated it.
- **Test code under `tests/`** is subject to the same rule. Test module docstrings, test
  function names, parameterization IDs, and inline comments MUST describe the behavior
  under test, not the methodology, spec section, or task ID that motivated it.
- **User-facing repository documentation** — `README.md`, `CHANGELOG.md`, `SECURITY.md`,
  `CONTRIBUTING.md`, example READMEs under `examples/`, generated API reference output,
  and any other Markdown that ships in the sdist or is rendered on PyPI / project sites —
  MUST NOT mention `speckit`, `.specify/`, the constitution, constitution principles, or
  paths under `specs/`. If a rule's *rationale* needs to appear in `CONTRIBUTING.md`,
  restate it locally; do not link to the constitution as the canonical source.
- **PyPI distribution contents.** The `[tool.hatch.build.targets.sdist]` `include` list and
  the wheel packages list MUST NOT pull in `.specify/`, `specs/`, or any other directory
  whose purpose is to hold methodology artifacts. The default-deny stance is: if a path is
  part of the development methodology, it does not ship.
- **Exception scope is narrow and explicit.** A permitted reference MUST live in a file or
  section whose declared subject is "how to use speckit *as a maintainer of this
  repository*." The exception applies to:
  1. A dedicated file such as `docs/speckit-usage.md` (or any equivalently-named file)
     whose entire purpose is documenting the maintainer workflow with speckit, and which
     MUST NOT be included in the PyPI sdist or wheel.
  2. A clearly-labelled, self-contained section within a maintainer-only document
     (e.g. an internal `docs/maintainers/` doc) that is likewise not shipped to PyPI.
  The exception does NOT extend to source code, test code, `README.md`, `CHANGELOG.md`,
  `SECURITY.md`, the published `CONTRIBUTING.md`, example READMEs, or any other file that
  reaches end users of the library.
- **Commit messages, PR titles, PR descriptions, and review comments** MAY reference the
  methodology, since they are workflow artifacts and are not part of the published
  package. The constitution itself, files under `.specify/`, and files under `specs/` are
  the methodology's home and are not bound by this rule.

Enforcement details (mechanisms) appear under "Methodology References in Published
Artifacts" in the Quality & Tooling Standards section below.

**Rationale**: Pyrmit's value proposition is a typed, fail-closed authorization library.
Mentioning the maintainers' internal planning tool in a user-facing docstring or README
leaks implementation noise into the user experience, ties the library's public identity to
a specific agent-assisted workflow that may change, and creates dead references when
external readers encounter terminology they have no context for. Cleaner still: a user
auditing `pyrmit` for security should be able to read its source and tests as a
domain-focused authorization library, not as the output of a particular development
process. Keeping the published surface methodology-agnostic preserves a professional
library boundary, narrows the cognitive surface area for new contributors and security
auditors, and prevents the published package from becoming an inadvertent advertisement
for — or hostage to — any single workflow tool.

## Quality & Tooling Standards

The following tooling gates are part of the constitutional contract and MUST run in CI on
every pull request:

- **Formatting & linting**: `ruff format` and `ruff check` MUST pass with zero diagnostics.
  Disabling individual rules is allowed only with a justifying code comment.
- **Type checking**: `mypy` (strict configuration) MUST pass with zero errors. See
  Principle II for prohibitions on suppression comments.
- **Testing**: `pytest` MUST pass; coverage tooling (`coverage`, `pytest-cov`) MUST be run
  and reported. New code SHOULD achieve ≥90% branch coverage; drops below the project's
  current coverage floor MUST be justified.
- **Dependency hygiene**: `deptry` MUST pass; unused or undeclared dependencies are
  defects.
- **Pre-commit**: The `.pre-commit-config.yaml` hooks MUST run clean locally before push.
  Skipping hooks via `--no-verify` is FORBIDDEN unless the maintainer explicitly approves
  it for a specific commit.
- **Markdown**: `markdownlint-cli2` MUST pass on all repo Markdown except files under `specs/`
  (which are working drafts; see Principle V). The exception MUST live in
  `.markdownlint-cli2.yaml` so it is enforced by tooling, not by reviewer memory.
- **Docstrings**: Every public module, class, function, and method MUST carry a docstring in
  **Google docstring conventions**, enforced by `ruff`'s `pydocstyle` plugin
  (`[tool.ruff.lint.pydocstyle] convention = "google"`, already configured in `pyproject.toml`).
  Private helpers (leading underscore) MAY omit a docstring when their name is self-describing,
  but SHOULD include one when the function does anything subtle. Docstrings MUST describe the
  contract (what the caller can rely on), not the implementation.
- **Commit hygiene**: Commits MUST follow Conventional Commits (enforced via Commitizen).

### Methodology References in Published Artifacts

Principle VII (Methodology-Agnostic Published Artifacts) is enforced primarily in code
review, supported by a documented grep that any contributor or reviewer can run locally.
There is no required CI gate for this rule; the cost of a generous-by-design grep failing
on legitimate prose was judged higher than the marginal value it adds over reviewer
attention.

- **Scope.** The following paths MUST be free of methodology references: `src/**`,
  `tests/**`, `README.md`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`,
  `examples/**/*.md`, `examples/**/*.py`, `docs/**` (with the narrow carve-out below),
  and any other file that is part of the sdist `include` list in `pyproject.toml` or
  the wheel `packages` list. Internal development files — `.pre-commit-config.yaml`,
  `pyproject.toml` comments, project scripts under `scripts/` — SHOULD also avoid
  methodology references for coherence, even though they do not ship.
- **Forbidden token set** (case-insensitive where the underlying token is case-insensitive
  in practice, otherwise literal): `speckit`, `.specify`, `specify/templates`, `specs/`,
  `constitution`, `Principle I` through `Principle VII` (any roman-numeral or
  arabic-numeral form when adjacent to the word "Principle"), the regex-style pattern
  `FR-\d+`, `SC-\d{3,}`, `research R-\d+`, and the regex-style pattern `T\d{3,}[a-z]?`
  when occurring as a task identifier in a docstring, comment, or Markdown context.
  Also forbidden: citations of internal design artifacts and their section anchors —
  `spec §N.N`, `spec.md`, "the spec" (when referring to the feature spec rather than an
  external standard such as a PEP or RFC), `data-model.md`, `contracts/<anything>.md`,
  `plan.md`, `tasks.md`, `research.md`, `quickstart.md` — and user-story identifiers
  (`User Story N`, `Story N`, `US1`/`US2`/...). Names defined only by an internal
  artifact (e.g. "Pattern A" / "Pattern B" for subject-type parameterization) MUST be
  restated in self-describing terms (e.g. "union pattern" / "marker-base pattern").
- **Path-pattern exceptions.** A tooling configuration file MAY contain a literal path
  pattern (e.g. `specs/**`, `\.specify/scripts/.*`) when the pattern is *required* to
  scope a linter, formatter, or pre-commit hook. The exception is narrow: only the path
  pattern itself is permitted; any surrounding prose, hook name, or description MUST
  still be free of methodology references.
- **The carve-out for maintainer documentation.** A dedicated file whose entire declared
  subject is the maintainer-facing workflow (e.g. `docs/speckit-usage.md`, exact filename
  chosen by the maintainer applying this principle) MAY contain methodology references,
  but MUST be excluded from the PyPI sdist / wheel by the `pyproject.toml` build
  configuration.
- **Sdist / wheel audit.** `pyproject.toml`'s `[tool.hatch.build.targets.sdist]` `include`
  list and `[tool.hatch.build.targets.wheel]` `packages` list MUST be reviewed on every
  amendment to either list to ensure no methodology directory (`.specify/`, `specs/`,
  the maintainer-doc carve-out file) is silently pulled in.
- **Restating rationale in domain terms.** When a contributor needs to capture a
  rationale in source that was originally motivated by a constitution principle, the
  contributor MUST restate the rule in domain terms (e.g. "fail closed on
  subject-resolution failure", "log via the module-scoped logger and never call
  basicConfig"). Citing "Principle V" satisfies neither this rule nor a future reader
  who lacks the governance context.
- **The contributor-facing grep recipe** (not a CI gate; a documentation aid):

  ```sh
  grep -rn -iE \
      'speckit|\.specify|specify/templates|specs/|constitution|Principle [IVX]+|FR-[0-9]+|research R-[0-9]+|SC-[0-9]{3}|\bT[0-9]{3,}[a-z]?\b|spec §|spec\.md|the spec\b|data-model|contracts/|plan\.md|tasks\.md|research\.md|quickstart\.md|user stor|\bUS[0-9]+\b|\bstory [0-9]|pattern [AB]\b' \
      --include='*.py' --include='*.md' \
      src/ tests/ README.md CHANGELOG.md CONTRIBUTING.md SECURITY.md examples/
  ```

  A clean run is the expected baseline; any match should be removed or, if it falls under
  one of the narrow exceptions above, justified at code review time.

The token set above is intentionally generous: false positives are cheap to silence in
the grep recipe or by restating the prose, while false negatives — methodology
references that slip into the published package — are the exact failure mode this rule
exists to prevent.

### Runtime Dependency Policy

Pyrmit MUST remain dependency-free at runtime. The only runtime dependencies permitted are
**version-specific stdlib backports** — packages that exist solely to provide, on older
supported Python interpreters, a feature that is already present in the standard library of
newer supported interpreters. Each such dependency MUST be gated by a `python_version`
environment marker so that it is *not* installed on interpreters whose stdlib already
provides the feature.

Concretely, this means:

- A new runtime dependency that is NOT a stdlib backport requires a constitution amendment.
  "It would be convenient" is not a sufficient justification; convenience belongs in
  optional extras (`[project.optional-dependencies]`) or in the developer toolchain
  (`[dependency-groups]`), not in the core install.
- Optional framework adapters (e.g., Strawberry, FastAPI, SQLAlchemy integrations) MUST be
  declared as extras under `[project.optional-dependencies]` so that the base install
  remains zero-dependency on modern Python.
- Developer-only dependencies (linters, test frameworks, build tooling) MUST live in
  `[dependency-groups]` and are unconstrained by this policy.
- `deptry` MUST be configured to detect drift between the declared runtime surface and the
  imports in `src/`; any newly-imported third-party module in library code MUST be
  accompanied by an amendment PR.

**Rationale**: An authorization library is depended upon by every layer of the consumer's
stack. Each runtime dependency Pyrmit takes on becomes a transitive dependency of every
consuming application, expanding supply-chain attack surface and version-pinning friction
across the ecosystem. Forcing the cost of a new runtime dependency through a constitution
amendment keeps the install footprint honest and makes "do we *need* this?" the default
question rather than the exception.

### Keyword-Only Arguments

Functions, methods, and constructors with more than two parameters MUST use Python's `*`
separator to require keyword arguments. This is enforced via `ruff`'s
`pylint.max-positional-args = 2`.

Exceptions (narrowly scoped, intentional):

1. **One or two parameters.** Functions with exactly one or two parameters MAY use positional
   arguments where it improves call-site readability (e.g., `add(a, b)`).
2. **Special methods.** `__init__` on `@dataclass(frozen=True)` value types, `__eq__`, `__lt__`,
   `__contains__`, `__getitem__`, and other dunder methods follow their standard signatures.
3. **Overrides of external APIs.** When overriding a method from an external library that does
   not itself enforce keyword-only arguments, the override MAY mirror the upstream signature so
   that the override remains substitutable. Document the exception with a one-line comment
   citing the upstream signature.

Each exception MUST be justified at the call site; the linter cannot tell intentional overrides
from oversight, so reviewers MUST verify the exception applies before approving.

### Floating-Point Numbers

`float` MUST NOT be used for any value where precision matters (durations, comparisons,
identifiers). Use `decimal.Decimal` or integer representations instead. `float` is permitted
only when an underlying API requires it.

### PEP 695 Generic Syntax

All generic type parameterization MUST use **PEP 695 syntax** (Python 3.12+, available across
every supported interpreter version of this project). The legacy `typing.TypeVar`,
`typing.ParamSpec`, `typing.Generic[T]`, and `: TypeAlias = …` forms are FORBIDDEN in new
code. When touching surrounding code, migrate legacy generics opportunistically — do not
ship new uses of the legacy forms.

Canonical forms:

| Construct | Required (PEP 695) | Forbidden (legacy) |
|---|---|---|
| Generic class | `class Container[T]:` | `class Container(Generic[T]):` |
| Generic function | `def first[T](xs: list[T]) -> T:` | module-level `T = TypeVar("T")` |
| Type alias | `type Vec[T] = list[T]` | `Vec: TypeAlias = list[T]` |
| Bounded type variable | `class Foo[T: SomeBase]:` | `T = TypeVar("T", bound=SomeBase)` |
| Constrained type variable | `class Foo[T: (str, int)]:` | `T = TypeVar("T", str, int)` |
| Param spec | `def deco[**P, R](fn: Callable[P, R]) -> Callable[P, R]:` | module-level `P = ParamSpec("P")` |

Permitted carve-outs (narrowly scoped):

1. **Mirroring an upstream API.** When subclassing a class or implementing a `Protocol` from
   an external library that was itself declared with `Generic[T]` / `TypeVar`, the
   subclass / implementer MAY mirror the upstream form so the relationship is recognized by
   the type checker. The mirrored form MUST be accompanied by an inline comment of the form
   `# pep695-exempt: <reason>` (e.g. `# pep695-exempt: mirrors strawberry.relay.Node`).
2. **`typing.Self`.** `Self` is permitted and is unaffected by this rule (it is not a
   `TypeVar` and has no PEP 695 equivalent).

Enforcement:

1. **Ruff pyupgrade rules.** The project's `[tool.ruff.lint] select` MUST include the
   pyupgrade rule set `"UP"` (at minimum `UP040` for type aliases, `UP046` for generic
   classes, and `UP047` for generic functions). These rules statically flag and auto-fix
   legacy generic declarations.
2. **Pre-commit grep.** The local pre-commit hook list MUST include a grep that fails on
   `from typing import TypeVar`, `from typing import ParamSpec`, `Generic[`, and
   `: TypeAlias` in files under `src/` and `tests/`, unless the offending line is annotated
   with `# pep695-exempt:`. This grep catches the cases where ruff cannot auto-rewrite
   (e.g. legacy patterns inside f-strings, docstrings, or comments-presented-as-code).

**Rationale**: PEP 695 syntax eliminates the disconnect between where a type variable is
declared and where it is used; it removes module-level `TypeVar` boilerplate; it expresses
bounds and constraints in the place they apply; and it produces more accurate type-checker
diagnostics because the variable's scope is intrinsic to its declaration. Pyrmit's entire
positioning is "typed end-to-end" — the engine's three-parameter generic shape
(`PolicyEngine[PrincipalT, ActionT, SubjectT]`) is documented in the source design as a
PEP 695 baseline (research R-1). Mixing legacy and modern generic forms creates avoidable
cognitive load for users reading the public API and the library's own source.

### No Emoji

Emoji MUST NOT appear in any project artifact, for any reason. This rule is absolute; there
is no narrow exception, no "but it's just a status marker", no "the template uses them".

Scope (non-exhaustive):

- Source code: string literals, identifiers, comments, docstrings, test names.
- Documentation: `README.md`, `docs/**`, example READMEs, CHANGELOG, SECURITY.md.
- Specifications: every file under `specs/`. The markdownlint exception in Principle V
  governs LINT rules only; it does NOT extend to emoji content.
- Commit messages, PR titles, PR descriptions, code review comments authored as part of
  the project workflow.
- Log messages, exception strings, error reasons, audit entries, and any structured
  output produced at runtime.
- File names, directory names, and branch names.

"Emoji" is defined per Unicode Technical Report 51 (UTS #51): any character carrying the
`Emoji_Presentation`, `Emoji`, `Emoji_Modifier_Base`, or `Extended_Pictographic` property,
including but not limited to glyphs from the "Symbols and Pictographs", "Emoticons",
"Transport and Map Symbols", "Miscellaneous Symbols and Pictographs", and
"Supplemental Symbols and Pictographs" Unicode blocks. Concretely forbidden examples:
check marks (`U+2705`), cross marks (`U+274C`), warning signs (`U+26A0`), the target
glyph (`U+1F3AF`), fire, rockets, hand gestures, hearts, sparkles, hourglass, gears.

Permitted Unicode that is NOT emoji and remains allowed:

- Box-drawing characters for ASCII-art diagrams (e.g. `─`, `│`, `┌`, `┐`, `└`, `┘`,
  `├`, `┤`, `┬`, `┴`, `┼`).
- Mathematical operators when precise notation is required (e.g. `≤`, `≥`, `×`, `÷`,
  `∞`, `≈`, `≠`).
- Accented letters, currency symbols, and other normal text characters.

For status markers in tables, checklists, and Sync Impact Reports, use ASCII tokens.
The canonical vocabulary is:

| Concept | Token |
|---|---|
| satisfied / done / passing | `OK` |
| in progress / partially done | `WIP` |
| pending / not yet started | `PENDING` |
| blocked / failing | `FAIL` |
| not applicable | `N/A` |
| informational note | `NOTE` |
| warning / caveat | `WARN` |

Enforcement: a pre-commit hook (and an equivalent CI step) MUST grep the repository for
characters matching the emoji property classes above and fail the commit / PR if any are
found. The hook script lives in the repo and is invoked from `.pre-commit-config.yaml`.

**Rationale**: emoji render inconsistently across platforms, fonts, terminal emulators,
code-search tooling, screen readers, and audit log sinks. They fragment text search (the
same concept gets indexed with and without the glyph), they break grep-friendly diffs,
they impair accessibility for assistive technologies, and they add visual noise that
works against the constitution's principles (Documentation as Contract,
Library-Grade Observability). Banning them by rule eliminates the recurring
"is this emoji OK here?" debate and removes an entire category of accidental ambiguity
from every artifact the project ships.

## Development Workflow & Review Gates

### Specification & Planning Flow

1. A feature begins with a spec under `specs/<###-feature-name>/spec.md` written against
   `.specify/templates/spec-template.md`.
2. An implementation plan under `specs/<###-feature-name>/plan.md` MUST include a
   **Constitution Check** section that explicitly addresses each of Principles I–VI.
3. Task lists under `specs/<###-feature-name>/tasks.md` MUST order TDD-first: failing tests
   precede implementation tasks for every user story.

### Review Gates

A pull request MUST NOT merge unless ALL of the following are demonstrably satisfied:

- Tests authored before implementation (verifiable from commit history or PR description).
- All CI gates green (ruff, mypy, pytest, coverage threshold, deptry, markdownlint).
- `README.md` updated for any public-surface change (Principle V).
- Security Considerations section present in the spec/plan for any new feature, and addressed
  in code review (Principle VI).
- No `Any`, no `# type: ignore`, no `# pyright: ignore` introduced (Principle II).
- No bare `assert` in test bodies except the narrow mypy-narrowing exception, with a
  comment (Principle III).
- Logging additions follow library-logging rules; no new top-level handlers, no
  `basicConfig`, no stdout/stderr writes (Principle IV).
- No new third-party runtime dependency introduced without a constitution amendment
  (Runtime Dependency Policy).
- No methodology references introduced into `src/`, `tests/`, `README.md`, `CHANGELOG.md`,
  `SECURITY.md`, the shipped `CONTRIBUTING.md`, example READMEs, or any other file that
  reaches end users of the library (Principle VII). Reviewers SHOULD run the
  contributor-facing grep recipe under "Methodology References in Published Artifacts"
  on any PR that touches docstrings, comments, or user-facing Markdown.

### Amendments

This constitution may be amended only via a pull request that:

1. Modifies `.specify/memory/constitution.md`.
2. Includes a Sync Impact Report at the top of the file describing the version bump and
   downstream artifacts affected.
3. Updates all dependent templates (`plan-template.md`, `spec-template.md`,
   `tasks-template.md`) and runtime guidance (`README.md`, agent guidance files) so they
   remain consistent.
4. Receives explicit maintainer approval — this constitution supersedes all other
   contributor guidelines and informal practices.

Versioning of this constitution follows semantic versioning:

- **MAJOR**: A principle is removed, redefined incompatibly, or a governance rule changes
  in a way that invalidates prior PR review criteria.
- **MINOR**: A new principle or section is added, or existing guidance is materially
  expanded.
- **PATCH**: Clarifications, wording fixes, or non-semantic refinements.

**Version**: 2.1.2 | **Ratified**: 2026-05-17 | **Last Amended**: 2026-06-06
