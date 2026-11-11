---
name: fleet-host
category: compute
tier: D
description: >-
  Grow and shrink an agent fleet by GCP VMs with one command each way: `fleet_host.py add <name>`
  creates a private (Tailscale + IAP only), agentic-vps-hardened Compute Engine host with a full lane
  toolchain, an LLM with no login (Gemini on Vertex through the VM service account), per-host
  revocable credentials and a T3 server linked to the fleet, and `remove <name>` drains it, saves
  unfinished work, revokes every credential with proof and deletes everything it created. Dry run by
  default; every step idempotent and re-runnable after a partial failure; all deployment specifics in
  one template file. USE WHEN adding heavy build/verify capacity to an agent fleet, spinning up or
  tearing down a cloud dev host for coding agents, "add a GCP host", "remove the fleet host",
  "grow/shrink the fleet", "mint per-host credentials", "revoke a host's tokens", or auditing that a
  removed host left nothing behind. NOT FOR hardening an existing non-GCP box (agentic-vps), one-off
  GPU jobs (remote-gpu, colab-remote), or Kubernetes/managed runners. Triggers on "fleet host",
  "add host", "remove host", "gcp fleet", "fleet_host", "grow the fleet".
latent_only: false
metadata:
  version: 0.2.0
  provenance: BRO-3651 (design, live drill 2026-11-10); BRO-3666 (login-free hosts, agent-operated, 2026-11-11)
---

# fleet-host — GCP VMs that join an agent fleet ready to work, and leave without a trace

Distilled from BRO-3651. A host joins **ready to run whole lanes, proofs included**, and leaves with
**every credential revoked and proven**. The procedure is code (`scripts/fleet_host.py`); this file is
the contract for running it and for extending it.

## The invariants

1. **The box is the sandbox** (composes `agentic-vps`). The agent gets passwordless sudo, docker,
   open egress and Claude `bypassPermissions`. Containment is the perimeter: the VPC admits only IAP,
   access is Tailscale with a tag whose hosts cannot reach the rest of the tailnet, a secret-free
   snapshot is taken before any credential lands, and `agentic-vps/scripts/verify.py` must pass.
2. **No long-lived secret in any environment.** Tokens live in 0600 files. A `~/.local/bin/<cli>`
   wrapper loads one token into its own process only; shells export only non-secret ids.
3. **Per-host credentials, never copied when they rotate.** Vercel and Neon are minted per host (Neon
   proven unable to read production before delivery). Claude, Codex and gh are interactive logins on the
   host: copying a refresh token breaks one of the two hosts. A shared key (Linear) is an explicit
   template choice.
4. **A ledger, not a hope.** A minted id is recorded before anything else can fail. A record is dropped
   only when the credential is *proven* gone. "Unknown" is never "absent": an unreachable host or a
   failed read blocks, it never counts as revoked.
5. **Never destroy accepted work.** Removal waits for active runs, then pushes dirty trees, local-only
   branches and detached HEADs to `wip/<host>/<worktree>/<branch>-<sha>` (`--push-wip`); otherwise it stops.
6. **An owner step stops the run.** With `--apply`, any `owner`, `blocked` or `FAIL` step ends the run;
   re-running resumes there.
7. **Useful before any login.** Gemini on Vertex (the VM service account, no key file), T3, the verify
   gate, the T3 link and registration all come before the interactive logins, which are the last step
   and gate nothing.
8. **Agents operate it; the owner approves grants.** The owner never runs the tool. Logins are device
   codes the agent relays; the owner only approves them in a browser. A new host is proposed with
   demand evidence, never added automatically.

## Procedure

1. **Template.** Copy `scripts/fleet-host/template.example.json` to `~/.config/fleet-host/template.json`
   (or pass `--template`) and fill in every `<...>`: GCP project and admin account, tailnet tag and
   suffix, repos, the credential set, fleet setpoints. It holds no secrets.
2. **One-time owner setup** (each through T3 `request_secret` into the Mac Keychain, never chat):
   - the tailnet policy owns the tag, and the allow-all source excludes it;
   - a Tailscale OAuth client (`devices:core`, `auth_keys`, limited to the tag);
   - a full-account Vercel *minter* token (the CLI's OAuth login cannot mint: 403);
   - `gcloud auth login` and `neonctl auth` on the Mac;
   - a spend approval: `$FLEET_DIR/meta/fleet-hosts/APPROVAL.json` with the approved shapes and ceiling.
3. **Dry run first:** `python3 scripts/fleet_host.py add <name>`. Every step prints `ok`, `would`,
   `owner` or `blocked` against the live state.
4. **Add:** `python3 scripts/fleet_host.py add <name> --apply`, run by the agent.
   - The host comes up with Gemini on Vertex and a `gemini-vertex` T3 provider.
   - The `t3-link` step links it automatically: it runs `t3 pair` on the host and pipes the token into the
     Mac's `t3 environment link`, so the token is never printed.
   - `host-key` pins the VM's ssh key only if it matches the serial console.
   - The last step, `cred:logins`, has no terminal. It starts each login (gh, codex, claude) in a
     `login-<tool>` tmux session on the host and returns the link and code as an `owner` detail. The
     agent relays them to the owner, who approves in a browser. Codes live 15 min, so regenerate them
     right before asking.
   - Claude ends with a code shown in the browser. Deliver it with
     `fleet_host.py login-code <name> claude --code-file <file>` (from a secure-input file; the code
     goes over ssh stdin).
   - Re-run `add` until it reports N/N.
5. **Wake on demand.** A host stops itself when idle. `fleet_host.py start <name> --apply [--awake 0..240]`
   starts it and holds it awake 60 min by default. Idle stop also counts a pending login as busy.
   `converge` (inside `add`) carries template and script changes to a live host.
6. **Remove:** `python3 scripts/fleet_host.py remove <name> --apply [--push-wip]`. The receipt in
   `$FLEET_DIR/meta/fleet-hosts/<name>/remove-<UTC>.json` lists every step and every revocation proof.

Also: `start` / `stop <name>` (stop refuses while a run or heavy job is active) and
`creds` / `revoke-creds <host>` for any ssh-reachable host.

## Extending

| To add | Change |
|---|---|
| a repo on every host | `repos` in the template |
| a minted credential | a `Minted` subclass in `scripts/fleet_host_creds.py` (`mint`, `listed`, `delete`, optional `scope_ok`, `env`, `wrapper`) plus its name in `credentials.enabled` |
| an interactive login | an entry in `_LOGIN_CMDS` (status, login, logout), in `credentials.logins`, and in `RELAY` (how to read its link/code from the pane) |
| the default LLM | `llm.vertex` in the template (location, Gemini CLI version, models, probe model); `enabled: false` removes it on converge |
| a machine shape | `shapes` (vCPU, GiB); the heavy-slot count follows from it |
| a different cloud project or fleet | another template |

Revocation always covers every credential kind, so a record left by an older template is still revoked.

## Evidence (live drill, e2-standard-8, 2026-11-10)

- Ready in about 2 minutes with all 16 tools present.
- The tailnet tag isolates the host: it cannot reach the other hosts' `:22`.
- 0 secrets in a login shell.
- `verify.py` PASS, including the public `:22` probe.
- A 3 GiB `tsc --noEmit` ran in 9.5 s; two in parallel took 14.4 s each with no swap. The 8-thread,
  15 GB host it relieves ran past 2 h with swap full on the same pair.
- Remove 15/15. An independent re-check found everything gone: Vercel token 404, Neon key unlisted,
  and the service account, IAM bindings, disk, snapshot, secrets and tailnet node all absent.

The drill caught three bugs that review did not:
- the Claude installer pre-writes `settings.json`, so the settings are now merged into it;
- `npx t3 service install` lays down no launcher, so the tool links one;
- a deleted service account answers `describe` with 403, so absence is proven from the account list.

## Evidence (login-free and agent-operated, 2026-11-11)

- With no login at all, the host called Vertex using only its service account: `gemini-4-argon`,
  `gemini-3.8-flash` and `gemini-2.5-flash` all returned 200.
- The T3 link was automatic. A task delegated from the Mac's T3 ran on the host on Gemini, and three
  rounds of cross-model review ran there too.
- The relayed logins were approved in a browser: Claude, Codex and gh were logged in, the repos were
  cloned, and `add` reached 24/24.
- Before the fix, idle stop powered the host off mid-login. After it, the journal shows `busy: login
  awake`, and an awake hold more than 4 h ahead is ignored.

## Validation

```
python3 -m pytest tests/ -v        # 47 tests: ledger, revocation proofs, WIP rescue on real git repos,
                                   # remove safety, template, login relay, host-key pinning, converge, wake
bash -n scripts/fleet-host/startup.sh scripts/fleet-host/idle-stop.sh
```

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "Copy the Mac's tokens, it's faster." | Rotating OAuth tokens break one host when the other refreshes. Static tokens copied from the Mac carry its full scope and cannot be revoked per host. Mint, or log in on the host. |
| "The host is unreachable, so its credentials are gone." | Only a NOT_FOUND instance proves the disk is gone. An unreachable host blocks. |
| "Export the token so every tool sees it." | Every child process, postinstall script and error dump sees it too. Use the per-CLI wrapper. |
| "`--push-wip` will sort it out." | It refuses to continue until a re-scan is clean. A failed scan is unknown, never clean. |
| "Ask the owner to run `add` from a terminal for the logins." | The owner does not run the tool. Relay the device codes; the owner approves in a browser. |
| "Accept whatever host key answers; it's our VM." | A re-created host keeps its name and gets a new key. Pin only the key the serial console shows. |
