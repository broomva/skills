# Security Policy

## Supported Versions

| Version            | Supported          |
| ------------------ | ------------------ |
| `0.1.x-pre` (current Phase 1 / 2) | Yes |
| Older               | No  |

The project is in pre-release. Each new tag may supersede the previous one.
The latest tag on `main` is always the supported line.

## Reporting a Vulnerability

If you discover a security vulnerability — for example, a way to bypass the
P6 tenant-data isolation hook, leak tenant-identifying markers through the
anonymization canary, or escape the L1–L5 release-gate linter — please do
**not** open a public GitHub issue.

Instead, email **<contact@broomva.tech>** with:

- A description of the vulnerability
- Steps to reproduce
- The affected version (`phronesis --version`)
- Any suggested mitigation

We will acknowledge receipt within 7 days and aim to publish a fix or
mitigation within 30 days for high-severity issues.

## Disclosure Policy

We follow a coordinated disclosure model. After a fix is published and
released:

1. The vulnerability is described in the CHANGELOG entry for that release.
2. A GitHub Security Advisory is published with the CVE (when applicable).
3. Credit is given to the reporter unless they request otherwise.

## Out of Scope

The following are explicitly **out of scope** for security reports — these
are intentional behaviors documented in the design spec:

- Pre-commit and pre-push hooks can be bypassed via `git commit --no-verify`
  or `git push --no-verify`. CI enforces the same gates server-side.
- The L1–L5 linter rules are advisory at construction time and enforced at
  release-gate time. Tooling that constructs Engagement aggregates manually
  outside the stage runners can produce technically-malformed engagements;
  the linter's job is to surface those at the release gate, not to prevent
  their construction.
- The CLI `render --ungated` flag intentionally bypasses the lint gate for
  debugging. Production publication paths use `render` (gated by default).
