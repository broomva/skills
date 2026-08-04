# Security policy

## Reporting a vulnerability

Report privately via [GitHub Security Advisories][advisory] on this repository.
Please do not open a public issue for a vulnerability.

[advisory]: https://github.com/broomva/skills/security/advisories/new

Include what an attacker gains, the steps to reproduce, and the version or
commit. You will get an acknowledgement within a few days. Keel is maintained
by one person, so please allow reasonable time before disclosing publicly.

## What Keel does on your machine

Worth stating plainly, because it informs what counts as a vulnerability here.

**Keel reads your repository and executes probes.** Probes are small scripts —
shipped in `skills/keel/probes/`, or minted locally into
`~/.config/keel/probes/` — that classify recurring verification shapes without
a model call. They are executed code.

This has two consequences:

1. **Review probes like you review dependencies.** A probe from a pull request
   is untrusted code until someone has read it. That is the point of shipping
   probes as small reviewable scripts rather than as an opaque model — the
   review is possible — but it only helps if the review happens.
2. **Keel runs against a target you point it at.** It reads CI definitions,
   task scripts, and configuration. Do not run it against a repository you
   would not otherwise clone and open in an editor.

### The sandbox is macOS-only. Stated plainly, because the difference is large.

Probe code runs in a child process. On macOS that child is confined by
`/usr/bin/sandbox-exec`; **on every other platform it is not confined at all**,
because the mechanism does not exist there. What the child gets is a stripped
environment — no inherited credentials — and a kill-timer held by the parent.
That is real, and it is much less than confinement.

| | macOS | Linux · Windows |
|---|---|---|
| Filesystem writes | denied | **allowed** |
| Network | denied | **allowed** |
| Subprocess execution | denied except `bun` | **allowed** |
| `~/.ssh`, `~/.aws`, `~/.gnupg`, `~/.config/gh`, `~/.netrc` reads | denied | **allowed** |
| Other file reads | allowed | allowed |
| Inherited environment | stripped | stripped |
| Wall-clock kill-timer | enforced by the parent | enforced by the parent |

So on Linux and Windows, **a probe can do anything you can do.** The
denylist column above is also a denylist, not coverage: on macOS a probe can
still read other credential-shaped files, and a probe's verdict text lands in
`report.json`, so a read is exfiltratable by a probe that chooses to.

Treat an unreviewed probe on a non-macOS machine as you would treat running an
unreviewed script from the internet, because that is what it is.

### Keel ignores configuration coming from the target

Bun loads `.env` from the working directory, and when you point Keel at a
target that directory is usually the target itself. A repository under
measurement therefore must not be able to set Keel's own environment: it could
otherwise disable the sandbox and choose which directory of executable code
gets loaded.

So any `KEEL_*` variable defined by a dotenv file in the working directory is
**dropped before it is read**, and the run records that it was dropped. Export
the variable in your shell if you meant it — your shell is outside the write
boundary of the thing being measured, and a file in the target is not.

Keel does not transmit your repository anywhere. Classification that cannot be
handled by a probe is performed by whichever agent harness you are running
Keel inside, under that harness's own model and network policy — so the
relevant data-handling terms are your agent provider's, not Keel's.

## In scope

- Probe execution escaping its intended sandbox.
- A crafted target repository causing code execution during `gather`.
- A crafted `report.json` causing code execution in the HTML renderer, or
  script injection into the rendered artifact.
- Path traversal writing outside the intended output location.

## Not in scope

- **Keel classifying a node incorrectly.** That is a correctness bug and a
  genuinely useful one — file it as a *Misclassification* issue instead.
- A low grounding ratio on your own repository. That is a finding, not a flaw.
- Vulnerabilities in the agent harness Keel runs inside; report those upstream.

## Supported versions

Keel ships as an agent skill installed from `main` via `npx skills add`. Fixes
land on `main`; there are no maintained release branches. Re-run
`npx skills add broomva/skills --skill keel` to update.
