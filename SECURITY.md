# Security policy

`pyrmit` is an authorization library; bugs in its core fail-closed,
denial-surface, or audit-integrity behavior are treated as security
issues even when no exploit is demonstrated.

## Supported versions

The library is pre-1.0. Only the latest published `0.x` release is
supported for security fixes.

| Version | Supported          |
| ------- | ------------------ |
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a vulnerability

Please report suspected vulnerabilities **privately** to
<conor.heine@gmail.com>. Do not open a public GitHub issue for
security-sensitive reports.

Please include:

- A description of the vulnerability and its impact.
- A minimal reproduction (code snippet, failing test, or PoC).
- The affected `pyrmit` version and Python version.
- Any suggested remediation.

You can expect:

- An acknowledgment within 72 hours.
- A status update within 7 days.
- A coordinated disclosure window of up to 90 days, with credit in the
  release notes if you wish.

## Scope

In scope:

- `PolicyEngine` decision correctness, fail-closed behavior, audit
  dispatch and audit-failure handling.
- Adapter denial surfaces (Strawberry NULL/FORBIDDEN/NOT_FOUND, FastAPI
  HTTP translation, SQLAlchemy visibility scope).
- Cache-coherence and cross-request isolation in `CachedEntitlementProvider`
  and the Strawberry adapter's principal cache.
- Information leakage via decision reasons, audit metadata, or assertion
  messages.

Out of scope:

- Vulnerabilities in third-party dependencies (please report upstream).
- Issues that require an attacker to already have code-execution inside
  the application process.
- Application-level misuse of the library (e.g. a custom policy function
  that itself contains an authorization bug).
