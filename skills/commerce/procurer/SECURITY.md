# Security Policy

## Supported Versions

| Version | Supported |
| --- | --- |
| `0.1.x` (current) | Yes |
| Older | No |

This is a pre-1.0 skill. The latest tag on `main` is always the supported line.

## Reporting a Vulnerability

If you discover a security issue, please do **not** open a public GitHub issue.

Email **<contact@broomva.tech>** with:

- A description of the issue.
- Reproduction steps if applicable.
- The version (tag) you observed it on.
- Your suggested severity (low / medium / high / critical).

You should receive an initial acknowledgment within 72 hours. We will work with you on a coordinated disclosure timeline.

## Threat model — what counts as a security issue

The procurer skill itself does not handle credentials, network sockets, persistent state, or untrusted code execution. Realistic security concerns are narrow:

- **Validator bypass**: `scripts/validate_report.py` declaring a malformed report as valid (e.g., accepting non-numeric prices, accepting `confidence: 2.0`, accepting unresolved footnotes). This is the most likely real issue and we treat it seriously because users downstream rely on the validator to gate procurement decisions.
- **Path traversal in the validator**: the script reads a single file argument; if a future change introduces directory traversal or arbitrary file reads, that's a bug we want to know about.
- **Prompt injection through example content**: the worked examples in `assets/examples/` are read into agent context. If a maliciously-crafted example could exfiltrate data or override safety policy from a downstream user's workspace, that's a concern.

Out of scope (please don't report):

- **Hallucinated prices** in agent output. The grounding discipline is *recommended* by the skill; the skill cannot prevent an underlying LLM from violating it. Hallucinated numbers are a research-quality issue, not a security issue.
- **Outdated supplier shortlists** in `assets/examples/construction-materials-co.md`. Suppliers go in and out of business; we accept staleness and welcome PRs.
- **Validator strictness** disagreements (e.g., "I think confidence should be allowed at 1.5"). Open a regular issue.

## Updates

When a security issue is fixed, we publish:

1. A patch release with a bumped version in `CHANGELOG.md`.
2. A GitHub Security Advisory at <https://github.com/broomva/procurer/security/advisories>.

Subscribe to repo releases to be notified.
