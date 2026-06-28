# agentic-vps

Provision and harden a fresh Linux VPS into an **autonomous-agent dev host** using
the **capability-preserving model**: the box *is* the sandbox — full agent autonomy
inside it, contained by isolation (non-root user + VPN-only access + snapshot +
no-long-lived-secrets), **not** by restricting the agent.

> Standing constraint: *"secure but don't limit capability/autonomy."*

## Install

```
npx skills add broomva/skills --skill agentic-vps
```

## Use

```
# 1. provision (idempotent, run as root)
ssh root@<host> 'AGENT_USER=agent bash -s' < scripts/provision.sh

# 2. perimeter — VPN up, VERIFY in a 2nd session, THEN close public SSH
#    (validate the plan is lockout-safe first)
python3 scripts/staging_check.py snapshot oob_console_confirmed vpn_up \
        vpn_ssh_verified allow_vpn_ssh close_public_ssh

# 3. verify the capability-preserving invariants hold
python3 scripts/verify.py --host agent@<tailnet-ip> --public-ip <public-ip>
```

## What's deterministic

| Script | Role | Tested |
|---|---|---|
| `scripts/provision.sh` | idempotent install + caps + config | `bash -n` + shellcheck |
| `scripts/staging_check.py` | lockout-safe ordering gate (pure `check_sequence`) | `tests/test_staging_check.py` |
| `scripts/verify.py` | invariant evaluator (pure `evaluate`) | `tests/test_verify.py` |

The latent parts (which provider, which toolchains, how the user authenticates)
stay in the agent's judgment per `SKILL.md`.

## See also
- `research/entities/pattern/capability-preserving-agent-host.md` — the pattern
- `research/entities/concept/lethal-trifecta-denial.md` — the security model
- `docs/security/2026-06-24-vps-agentic-hardening-playbook.html` — full rationale

Provenance: BRO-1550 (srv1692698 hardening session).
