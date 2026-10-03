# Rate limits: who does what

The active Claude credential is machine-wide: every session on the Mac reads the same keychain item.
So a rotation is never one session's decision. The balancer (`balance --auto`, kicked by the hooks)
is the only automatic actor, and it holds a machine-wide lock.

---

## 1. An agent hits a rate limit

Do nothing to the credentials. No `rotate`, no `switch`, no `login-headless`.

- The StopFailure hook has already recorded your session and queued a probe-confirmed failover.
- If a healthy account exists, the machine moves to it within the evaluation. Your session then
  adopts the new account in place within about 30 s, with no restart.
- End your turn with:

  ```
  ARC-STATUS: BLOCKED quota (rate limit on the active Claude account; provider-manager handles failover)
  ```

A tool error that mentions a rate limit (GitHub's API, a website's 429) is not a Claude limit, and it
is not a reason to touch credentials.

---

## 2. The orchestrator or operator

Look first:

```bash
PM=~/.agents/skills/provider-manager/scripts/provider_manager.py
python3 $PM usage          # OK / THROTTLED / AUTH_EXPIRED / NEEDS_LOGIN per account
python3 $PM state          # cooldown, hold, pending reports, lock holder
python3 $PM history --all  # recent decisions, refusals, probes
python3 $PM stalled        # sessions to resume
```

Then act on what you see:

| You see | Do |
|---|---|
| Active OK and under limits | Nothing. `THROTTLED` on the usage endpoint is not a limit. |
| Active limited, a standby `OK` and healthy | `rotate` (the probe confirms; switches safely), or wait for the balancer. |
| A standby `NEEDS_LOGIN` | `login-headless --email EMAIL` (replace `EMAIL` with that standby's email). For a standby, this renews only its copy and does not switch. Then `switch` if you want it. |
| You must move now, the probe disagrees | `rotate --force` (skips the probe and the gap; the switch still refuses a dead target). |
| A switch is refused: "matches no Orca copy and cannot be identified" | Run any `claude -p` (it refreshes the store under Claude Code's lock), then retry; or `switch --force` to discard that credential. |
| Want automatic switching off for a while | `hold --minutes N` (`hold --clear` to resume), or `"autoBalance": false` in the config. |

After a failover, resume the sessions in `stalled`: send each a prompt (Paseo: its agent id), or
`claude --resume <session>` from its cwd. Sessions that were still running moved without a restart.

---

## 3. What a switch guarantees

- The target is proven live before it is written: refreshed through its own copy if near expiry,
  then identity-checked.
- The outgoing account's live tokens are saved to its copy, so switching back is safe.
- The store is rewritten under Claude Code's refresh lock, `claudeAiOauth` only.
- Anything unexpected stops the switch and leaves the store as it was.
