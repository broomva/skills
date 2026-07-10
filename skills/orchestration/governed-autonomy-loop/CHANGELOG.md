# Changelog — governed-autonomy-loop

## 0.1.0 — 2026-07-10

Initial release. Skillified from the broomva ticket-dispatch governor (BRO-1740 +
BRO-1833 P1–P6) via `/skillify` (BRO-1849).

- **Deterministic core** (extracted from the reference prose, tested):
  `tick.sh` portable scheduler, `loop_state.py` (in-flight fold, P5 reseed gate,
  busy-guard, arc-status contract), `validate_config.py` (fail-closed kill switch /
  DRY_RUN / num_or / partition guard), `denylist_check.py` (tracker write-surface
  coverage). 65 unit + integration tests + an E2E smoke.
- **Latent controller**: `runner-prompt.template.md` — the invariant spine factored
  from the Linear/merge specifics into four adapter slots.
- **Adapter contracts**: tracker / irreversible-act + enforcement / runtime /
  partition (`references/adapters.md`).
- **Server-side net**: `merge-gate.yml` aggregate gate + ruleset recipe
  (no-admin-bypass, prove-green-before-requiring).
- Fixed a watchdog fd-inheritance bug found while extracting the scheduler: the
  wall-clock watchdog subshell held a captured-pipe parent open via its sleep; now
  it redirects off the caller's stdout and reaps its own sleep on TERM.
- Shipped denylist adapter covers `create_initiative_label` (the reference tick.sh
  DRY_FLAGS omitted it — a real fail-open the coverage check catches).
