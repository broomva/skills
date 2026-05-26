# broomva-health

Personal health knowledge graph for the [Broomva stack][bstack]. Local-first
trace-ingest + synthesis + Obsidian-projection, behind a clean hexagonal
architecture that lets new sources (Apple Health, Whoop, Oura, CGM) drop in
as adapters with no changes to the application core.

**Status:** v0.2.0 (alpha) — Garmin submodule only; new sources scheduled
for v0.3+.
**Linear:** [BRO-1235][v1] (v1 ship) · [BRO-1236][v02] (v0.2 packaging)
**License:** MIT

[bstack]: https://github.com/broomva/bstack
[v1]: https://linear.app/broomva/issue/BRO-1235
[v02]: https://linear.app/broomva/issue/BRO-1236

---

## Install

Pick the path that matches what you want:

### A — Full CLI + agent skill (recommended)

```bash
# One-shot from a clone:
git clone https://github.com/broomva/health.git && cd health
bash install.sh

# Or one-shot from the web (no clone):
curl -fsSL https://raw.githubusercontent.com/broomva/health/main/install.sh | bash
```

This installs the `health` CLI to `~/.local/bin/health` (symlinked from a
private venv at `~/.local/share/broomva-health/.venv`). Run `health --help`
after install to confirm. Re-running `install.sh` upgrades in place.

### B — Agent skill only (no Python CLI)

```bash
git clone https://github.com/broomva/health.git && cd health
bash install-skill.sh
```

Drops just the `SKILL.md` + `Workflows/` + `References/` into every detected
agent skill dir (`~/.claude/skills/`, `~/.cursor/skills/`, `~/.gemini/skills/`,
`~/.agents/skills/`). Use this when an agent needs to *see* the skill for
routing but the CLI runs on a different machine.

### C — Via `npx skills add` (multi-agent discovery)

```bash
npx skills add https://github.com/broomva/health --skill Health -g -y
```

Installs the skill manifest to `~/.agents/skills/health/` and symlinks into
30+ agent skill dirs. The Python CLI is NOT installed — run path A or `pip`
afterwards if you want the binary.

### D — Pure Python package (PyPI)

```bash
pip install 'broomva-health[garmin]'   # or uv pip install ...
```

Or with `uv`:

```bash
uv pip install 'broomva-health[garmin]'
```

Optional extras: `[garmin]` (Garmin source adapter), `[encrypted]`
(SQLCipher trace DB — v1.1+), `[keychain]` (macOS Keychain token store),
`[dev]` (pytest + ruff + mypy + hypothesis).

---

## Quick start

```bash
health auth login                  # one-time, with MFA
health doctor                      # verifies install + paths
health sync                        # incremental pull
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

By default the trace DB is unencrypted SQLite at `~/broomva/health/traces/`.
SQLCipher upgrade path is documented in [`References/privacy-architecture.md`](References/privacy-architecture.md).
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

233 tests across unit + property (Hypothesis) + integration. Run in under 1s
on a warm cache. CI matrix covers Python 3.12 and 3.13.

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
