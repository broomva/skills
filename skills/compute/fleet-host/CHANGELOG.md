# Changelog

## [0.2.0] — 2026-11-11
- Login-free hosts (BRO-3666):
  - Gemini CLI on Vertex through the VM service account, plus a `gemini-vertex` T3 provider;
    `llm:vertex` proves one call;
  - the template gains an `llm.vertex` block.
- T3 link automated: `t3 pair` piped into `t3 environment link`; the environment id is recorded. A `~/scratch`
  T3 project lets the host take tasks before gh is logged in.
- Agent-operated logins:
  - relayed device codes from `login-<tool>` tmux sessions, which are bounded and never reused once spent;
  - `login-code` delivers Claude's paste code on ssh stdin;
  - logins are now the last step.
- `host-key` pins the VM key against the serial console; a woken host is verified by strict ssh; `remove`
  forgets the key. `converge` re-applies template and script changes to a live host.
- `start --awake` holds the host awake. Idle stop counts a pending login and the awake hold as busy, and
  ignores a hold more than 4 h ahead.
- Tests: 47.

## [0.1.0] — 2026-11-10
- Initial release. Distilled from BRO-3651: design, three cross-model review rounds (r3 PASS 9.5/10),
  and a live add/typecheck/remove drill on an e2-standard-8 host.
- `scripts/fleet_host.py` — add / remove / start / stop / status / creds / revoke-creds; dry run by
  default; idempotent steps; billable steps gated by an approval file.
- `scripts/fleet_host_creds.py` — per-host minted credentials with a pending-first ledger and
  revocation proofs; interactive logins over ssh -t; per-CLI wrappers keep tokens out of every env.
- `scripts/fleet-host/` — startup (agentic-vps model), heavy-job semaphore, idle stop, example template.
