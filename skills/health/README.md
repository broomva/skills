# broomva-health

Personal health knowledge graph for the [Broomva stack][bstack]. Local-first
trace-ingest + synthesis + Obsidian-projection, behind a clean hexagonal
architecture that lets new sources (Apple Health, Whoop, Oura, CGM) drop in
as adapters with no changes to the application core.

**Status:** v0.2.3 (alpha) — Garmin submodule only; new sources scheduled
for v0.3+.
**Home:** [`broomva/skills/skills/health`][home] (monorepo — Tier-2 agent skill)
**Linear:** [BRO-1235][v1] (v1 ship) · [BRO-1236][v02] (v0.2 packaging) · [BRO-1248][mono] (monorepo gap-close)
**License:** MIT

[bstack]: https://github.com/broomva/bstack
[home]: https://github.com/broomva/skills/tree/main/skills/health
[v1]: https://linear.app/broomva/issue/BRO-1235
[v02]: https://linear.app/broomva/issue/BRO-1236
[mono]: https://linear.app/broomva/issue/BRO-1248

---

## Install

This skill lives in the **`broomva/skills` monorepo**. Pick the path that
matches what you want:

### A — Via `npx skills add` (recommended — multi-agent discovery)

```bash
npx skills add broomva/skills --skill health -g -y
```

Installs the skill manifest (SKILL.md + Workflows + References + the
`install.sh`/`install-skill.sh` scripts) to `~/.agents/skills/health/` and
symlinks it into 30+ agent skill dirs (Claude Code, Cursor, Gemini CLI, …).
The Python CLI is NOT installed by this step — run path B afterwards if you
want the `health` binary.

### B — Full CLI (the `health` binary on your PATH)

```bash
# From the npx-installed skill (after path A):
bash ~/.agents/skills/health/install.sh

# Or one-shot from the web (no clone, no npx):
curl -fsSL https://raw.githubusercontent.com/broomva/skills/main/skills/health/install.sh | bash

# Or from a clone:
git clone https://github.com/broomva/skills.git && cd skills/skills/health
bash install.sh
```

This installs the `health` CLI to `~/.local/bin/health` (symlinked from a
private venv at `~/.local/share/broomva-health/.venv`). Run `health --help`
after install to confirm. Re-running `install.sh` upgrades in place.

### C — Agent skill only (no Python CLI, no npx)

```bash
git clone https://github.com/broomva/skills.git && cd skills/skills/health
bash install-skill.sh
```

Drops just the `SKILL.md` + `Workflows/` + `References/` into every detected
agent skill dir (`~/.claude/skills/`, `~/.cursor/skills/`, `~/.gemini/skills/`,
`~/.agents/skills/`). Use this when an agent needs to *see* the skill for
routing but the CLI runs on a different machine.

### D — Pure Python package (PyPI — planned)

> **Not yet published.** `broomva-health` is not on PyPI as of v0.2.3. The
> package builds cleanly (`uv build` → sdist + wheel); publication is tracked
> in [BRO-1248][mono]. Until then, use path B (the `install.sh` venv) for the
> CLI. Once published, this will work:

```bash
pip install 'broomva-health[garmin]'      # or: uv pip install 'broomva-health[garmin]'
```

Optional extras: `[garmin]` (Garmin source adapter), `[encrypted]`
(SQLCipher trace DB — v1.1+), `[keychain]` (macOS Keychain token store),
`[dev]` (pytest + ruff + mypy + hypothesis).

---

## Quick start

The default Garmin backend (`native`) is **in-house** — it calls Garmin's
`connectapi` through `garth`, riding an existing token. **The skill never
handles your Garmin password.** Mint a token once (interactive, straight to
Garmin), then bring it in-house:

```bash
uv tool install garmin-connect-cli && garmin-connect auth login   # one-time: mint a token
health auth import                                                # copy it into our store
```

Then:

```bash
health doctor                      # verifies install + paths
health sync                        # in-house garth pull → trace DB (steps, sleep, HRV, VO2max, …)
health status                      # token validity + last sync
health status                      # reflexive snapshot
health --format json context       # LLM-optimized aggregated dump
```

Global options precede subcommands (Typer convention):
`--format/-f {json,jsonl,csv,tsv,human}`, `--profile/-p`, `--fields`,
`--config/-c`, `--verbose/-v`, `--quiet/-q`, `--version/-V`.

Exit codes: `0` OK · `1` error · `2` auth-required (re-run `auth login`).

---

## Architecture (5-layer hex)

```
cli/  ─→  application/  ─→  ports/  ←─  adapters/
                                            └─ sources/      (Garmin · Apple · Whoop · Oura · CGM)
                                            └─ repositories/ (SQLite default · SQLCipher v1.1+)
                                            └─ projections/  (Obsidian daily-note · healthOS feed)
                                            └─ token_stores/ (filesystem · Keychain)
                                            └─ rate_limiters/ (token-bucket w/ JSON persistence)
                                            └─ mfa/          (prompt · env · Keychain)
domain/      pure Pydantic v2 — sample shapes, metric registry, results
synthesis/   derived views — HRV-CV, CTL/ATL/TSB, VO2max arc, custom recovery
config/      paths (XDG-aware) + settings (TOML + env)
migrations/  versioned SQL
```

The **domain** layer is pure (no I/O). The **ports** layer holds Protocol
interfaces. **Adapters** implement those protocols. The **application**
layer composes ports into use cases. The **CLI** wires concrete adapters
into the application at startup.

This separation is what lets a new source (e.g. Whoop) drop in as a single
file in `adapters/sources/` without touching anything else.

See [`References/architecture.md`](References/architecture.md) for the deep dive.

---

## Adding a new source

1. Add the enum member to `src/broomva_health/domain/source.py`.
2. Implement the `TraceSource` protocol in `src/broomva_health/adapters/sources/<name>.py`.
3. Register the adapter in `adapters/sources/_registry.py`.
4. (Optional) Add a CLI passthrough for source-specific endpoints.

Long-form walkthrough: [`References/extension-guide.md`](References/extension-guide.md).

---

## Privacy

By default the trace DB is unencrypted SQLite at `~/broomva/health/traces/`
(a local data directory — not the source repo). SQLCipher upgrade path is
documented in [`References/privacy-architecture.md`](References/privacy-architecture.md).
Tokens live at `~/.config/broomva-health/tokens/` with `0700` dir / `0600`
file permissions. The rate-limiter persists its state at
`~/.config/broomva-health/rate_limiter.state.json` so cross-process cron
invocations honor the 15-minute poll floor.

---

## Tests

```bash
make test           # unit tests
make test-e2e       # requires BROOMVA_HEALTH_E2E=1 + real Garmin credentials
make check          # lint + typecheck + test
```

233 tests across unit + property (Hypothesis) + integration. Run in under 3s
on a warm cache. CI matrix covers Python 3.12 and 3.13 via the monorepo's
path-filtered [`test-health.yml`](../../.github/workflows/test-health.yml)
workflow (runs only when `skills/health/**` changes).

---

## References

- [`SKILL.md`](SKILL.md) — agent-facing skill manifest
- [`Workflows/`](Workflows/) — per-workflow agent docs (Sync, Backfill, Status, DailyNote, TrainingLoad, RecoveryReview, VO2maxArc, Coaching)
- [`References/garmin-api-landscape-2026.md`](References/garmin-api-landscape-2026.md) — why we built this from scratch (garth deprecation, etc.)
- [`References/healthkit-data-model.md`](References/healthkit-data-model.md) — sample-type rationale
- [`References/architecture.md`](References/architecture.md) — hex architecture deep-dive
- [`References/extension-guide.md`](References/extension-guide.md) — how to add a new source
- [`References/rate-limit-discipline.md`](References/rate-limit-discipline.md) — what's safe; what bans accounts
- [`References/privacy-architecture.md`](References/privacy-architecture.md) — local-first model + SQLCipher path
- [`References/validation-evidence.md`](References/validation-evidence.md) — what synthesis metrics are HIGH-confidence

---

## License

MIT. See [`LICENSE`](LICENSE) (when added) or `pyproject.toml`.
