# Security Policy

## Reporting a vulnerability

**Do not open a public issue for security vulnerabilities.**

Report privately via GitHub's [private vulnerability reporting](https://github.com/broomva/skills/security/advisories/new)
(Security → Report a vulnerability), or email **devteam@getstimulus.ai** with
subject `SECURITY: broomva/skills`.

Please include: the affected skill, a description, reproduction steps, and the
impact. We aim to acknowledge within **72 hours** and to ship a fix or mitigation
for confirmed issues within **30 days**, coordinating disclosure with you.

## Scope

This monorepo hosts many independent skills. Of particular note:

- **Skills that read or store personal data** (e.g. `health` stores biometric
  traces locally at `~/broomva-health/`, mode `0700`, outside any git repo).
  Reports about credential handling, secret leakage into logs/commits, or
  data-at-rest exposure are in scope.
- **Skills that run shell/tooling or call external services.** Skills execute
  with full agent permissions — review a skill before use.

## Supported versions

Skills are versioned independently (`<skill>-vX.Y.Z`). Security fixes target the
latest released version of the affected skill; older tags are not patched.
