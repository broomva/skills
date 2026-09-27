# Provider Rotation & Rate-Limit Failover Playbook

This playbook defines the exact procedure for autonomous agents operating in this workspace when approaching or encountering Claude subscription rate limits.

---

## 1. Trigger Conditions

An agent should execute a provider rotation when:
1. **HTTP 429 Encountered**: Claude Code returns `rate_limit_error`, `overloaded_error`, or "You have reached your 5-hour limit".
2. **Proactive Rate Warning**: Claude warnings indicate < 5% quota remaining before a long-running batch job.
3. **Explicit Directive**: User or orchestration harness instructs credential rotation.

---

## 2. Autonomous Rotation Protocol

When a trigger condition occurs:

### Step 1: Check Current Status & Candidate Accounts
Run:
```bash
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py list --json
```

Examine the JSON response to see candidate accounts (`isActive: false`).

### Step 2: Execute Account Rotation
Run:
```bash
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py rotate --reason "rate_limit_429" --json
```

Expected output:
```json
{
  "success": true,
  "rotatedFrom": "devteam@getstimulus.ai",
  "rotatedTo": "team@getstimulus.ai",
  "reason": "rate_limit_429",
  "status": {
    "success": true,
    "switchedTo": "team@getstimulus.ai",
    "accountId": "5f5c518b-5edb-48a0-b2cd-8bce8a72f346"
  }
}
```

### Step 3: Handle Expired Tokens (Self-Healing Fallback)
If the rotation reports that credentials for the target account are missing or expired, run the headless login recovery:

```bash
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py login-headless --email <candidate_email>
```

This autonomously extracts the session from Arc/Chrome, performs the OAuth grant, and updates Keychain credentials without needing GUI or user intervention.

### Step 4: Verify & Resume
Verify the new credentials with a smoke test:
```bash
claude auth status
```

Resume the previous task on the newly activated account.

---

## 3. Switching to a Specific Account

To switch directly to a named account:
```bash
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py switch devteam@getstimulus.ai
# or
python3 ~/.agents/skills/provider-manager/scripts/provider_manager.py switch team@getstimulus.ai
```
