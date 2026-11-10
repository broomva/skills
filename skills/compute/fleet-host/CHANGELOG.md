# Changelog

## [0.1.0] — 2026-11-10
- Initial release. Distilled from BRO-3651: design, three cross-model review rounds (r3 PASS 9.5/10),
  and a live add/typecheck/remove drill on an e2-standard-8 host.
- `scripts/fleet_host.py` — add / remove / start / stop / status / creds / revoke-creds; dry run by
  default; idempotent steps; billable steps gated by an approval file.
- `scripts/fleet_host_creds.py` — per-host minted credentials with a pending-first ledger and
  revocation proofs; interactive logins over ssh -t; per-CLI wrappers keep tokens out of every env.
- `scripts/fleet-host/` — startup (agentic-vps model), heavy-job semaphore, idle stop, example template.
