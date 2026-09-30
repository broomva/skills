---
name: provider-manager
category: orchestration
description: >
  Autonomous AI provider and subscription management toolkit. Enables seamless
  account discovery, credential switching, automated zero-touch browser-session
  OAuth re-authentication, and proactive rate-limit failover rotation across
  Claude Code CLI, Orca, and macOS Keychain. Use when: switching Claude accounts,
  rotating providers on rate limits or 429 errors, inspecting subscription quotas
  or tier limits, headless re-authenticating Claude Code without physical display
  access, or synchronizing credentials between Orca and Claude Code. Triggers:
  "switch claude account", "rotate provider", "rate limit reached", "change claude credentials",
  "login headless", "orca credentials", "provider-manager", "subscription limit".
license: MIT
---

# Provider Manager

Autonomous provider and subscription credential manager for macOS environments running **Claude Code CLI** and **Orca**.

Transforms provider switching and re-authentication from a manual, GUI-dependent process into an **autonomous agent reflex**.

---

## Capabilities

1. **Multi-Account Discovery**: Enumerates all managed accounts, active status, organization UUIDs, subscription tiers (e.g. `max`, `pro`), and Keychain token health.
2. **Instant Account Switching**: Swaps active credentials in < 1 second across Claude Code (`~/.claude.json`, scoped/unscoped Keychain items) and Orca (`orca-data.json`, `Orca Claude Code Managed Credentials`).
3. **Headless Browser-Session OAuth**: Recovers active web sessions from Arc or Chrome profiles via macOS Keychain Safe Storage decryption, automatically authorizes Claude's PKCE OAuth flow, and injects the authorization code without physical screen or GUI access.
4. **Autonomous Rate-Limit Rotation**: When an agent hits an HTTP 429 (`rate_limit_error`) or 5-hour quota exhaustion, it rotates to the next available account and immediately resumes execution.

---

## Quick Reference Commands

All commands can be invoked directly from the CLI or within agent scripts:

```bash
# 1. List all accounts and token health
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py list

# Machine-readable JSON output
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py list --json

# 2. Check current active authentication & subscription status
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py status

# 3. View live 5-hour and 7-day usage telemetry across all accounts
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py usage
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py usage --force  # bypass cache

# 4. Proactively balance accounts (auto-switches if active exceeds threshold)
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py balance --threshold 85.0
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py balance --dry-run

# 5. Switch active credentials to another account
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py switch dev@company.com
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py switch team@company.com

# 6. Rotate to next available account (rate limit failover)
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py rotate --reason "rate_limit_429"

# 7. Headless zero-touch login via browser session
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py login-headless --email team@company.com

# 8. Claude Code Hook Dispatcher (SessionStart, PostToolUse, UserPromptSubmit)
python3 ~/.agents/skills/provider-manager/scripts/provider_manager_hook.py session-start
python3 ~/.agents/skills/provider-manager/scripts/provider_manager_hook.py post-tool-use
```

---

## Autonomous Agent Reflex: Rate Limit Failover

When an agent tool call or API request encounters a rate limit (HTTP 429 / quota exceeded):

1. **Rotate Credential**:
   ```bash
   python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py rotate --reason "rate_limit_429" --json
   ```
2. **If Token Missing/Expired**:
   ```bash
   python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py login-headless --email <candidate_email>
   ```
3. **Verify & Resume**:
   ```bash
   claude auth status
   ```
   Immediately retry the failed step.

---

## Architecture & Detailed References

* [references/architecture.md](references/architecture.md) — Comprehensive technical reference for Keychain schemas, Orca configuration, and Claude Web OAuth internals.
* [references/rotation-playbook.md](references/rotation-playbook.md) — Step-by-step procedures for autonomous agents when handling quota warnings and 429 errors.
