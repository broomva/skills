# Privacy architecture — local-first, owner-encrypted, no telemetry

The Health skill is the most privacy-sensitive component in the workspace. Sleep patterns, RHR, menstrual cycle data, glucose, medical-adjacent metrics — none of these belong on a third-party server unless the user explicitly puts them there. The model is **local-first by default**, with an opt-in encrypted upgrade path.

## The reference model — Apple HealthKit

Apple HealthKit on iOS keeps every `HKSample` in an encrypted local store. Apps must request explicit permission per `HKQuantityType` / `HKCategoryType` and the user can revoke at any time. Apple's own cloud sync (Health app → iCloud) is end-to-end encrypted; Apple cannot read the data either.

This is the posture we aspire to:
- **Data is local by default.** It lives on your disk, in your home directory, under permissions you control.
- **Tokens are minimal-scope** and stored at owner-only file permissions.
- **No telemetry, no analytics, no crash reporters, no "phone home".**
- **Network calls go only to the source vendor's own API.**
- **PII never reaches a log.**

References:
- Apple HealthKit privacy: https://developer.apple.com/documentation/healthkit/protecting_user_privacy
- Apple iCloud security overview: https://support.apple.com/en-us/HT202303

---

## v1 — SQLite at owner-only permissions

The default trace store is **unencrypted SQLite** at:

```
~/broomva/health/traces/garmin.db
~/broomva/health/traces/apple_health.db   # when v2 ships
~/broomva/health/traces/whoop.db          # when v2 ships
```

Per-source DB files are intentional — encryption / migration / rotation can be done per source without touching the others.

**Permissions:**
- The directory `~/broomva/health/` is created at the user's default umask (typically `0o755`).
- The trace DB files are created at the user's default umask.
- This is **fine for v1** because the directory is inside `$HOME` and not world-writable on any reasonable system. But it is not encryption.

**Threat model that v1 addresses:**
- Casual filesystem access (other users on the same machine cannot read your DB)
- Accidental backup-to-cloud (the path is under `~/broomva/`, which is **not** an iCloud-synced path per the workspace CLAUDE.md "Projects stay on local disk (never inside iCloud)" rule)

**Threat model that v1 does NOT address:**
- Disk theft / unlocked-machine theft (the DB is plaintext SQLite — `sqlite3` opens it directly)
- Adversaries with root on your machine (root can read anything)
- Cloud backup if you violate the no-iCloud rule

For the second category, use v1.1's SQLCipher path.

---

## v1.1 — SQLCipher upgrade path

When the `[encrypted]` extra is installed:

```bash
uv pip install "broomva-health[encrypted]"
```

…the optional dependency `pysqlcipher3` (https://pypi.org/project/pysqlcipher3/) is installed. The `HealthSettings.encrypt_db` flag is wired (`pyproject.toml` says "reserved for v1.1 SQLCipher integration; ignored in v1") and a new repository adapter `SQLCipherTraceRepository` is selected automatically.

**Key custody:**
- Encryption key is generated once (256-bit, `secrets.token_bytes(32)`).
- Key is stored in **macOS Keychain** (`keyring.set_password("broomva-health", "trace-db-key", key_b64)`) via the optional `[keychain]` extra.
- On Linux: key stored in the freedesktop Secret Service (GNOME Keyring / KWallet) via the same `keyring` library.
- On no-keyring systems: key stored at `~/.config/broomva-health/trace-db-key` mode `0o600` (worse than Keychain; documented in the warning at first launch).

**One-shot migration:**
- `health doctor --upgrade-encryption` runs the migration:
  1. Generate key, store in Keychain
  2. `ATTACH DATABASE 'plain.db' AS plain;` `ATTACH DATABASE 'encrypted.db' AS enc KEY 'x' '...';`
  3. Copy all tables (`INSERT INTO enc.tbl SELECT * FROM plain.tbl;`)
  4. Verify row counts match
  5. Move plain → backup; encrypted → primary
  6. Update `HealthSettings.encrypt_db = true`

Migration is idempotent; running it twice no-ops on the second call.

**Threat model added:**
- Disk theft / unlocked-machine theft (DB is encrypted at rest; Keychain unlock required to read)

**Threat model NOT addressed even with SQLCipher:**
- A logged-in adversary with your unlocked Keychain
- A keylogger
- A compromised Python process within your user account (it can read the key from Keychain)

These are out of scope for a personal-data skill; full-disk-encryption (FileVault on macOS, LUKS on Linux) is the right answer for them.

---

## Tokens

Token bundles are stored under:

```
~/.config/broomva-health/tokens/
  garmin.default.bundle
  garmin.<profile>.bundle
  whoop.default.bundle
  ...
```

**Permissions enforced at write time:**
- Directory: `0o700` — only owner can read
- Files: `0o600` — only owner can read

The `HealthPaths.ensure()` method explicitly `os.chmod(self.tokens_dir, 0o700)` after directory creation. The filesystem token store sets `0o600` on every file write.

**Bundle format:**
```python
class TokenBundle(BaseModel):
    source: Source
    profile: str
    raw_bytes: bytes        # opaque — whatever the source library hands us
    stored_at: datetime
    expires_at: datetime | None
```

`raw_bytes` is opaque to the Health skill — we don't introspect it. The source adapter knows how to serialize / deserialize. The bundle on disk is a pickled `TokenBundle` (or a simple length-prefixed binary; the exact format is an implementation detail of the filesystem adapter).

**Keychain alternative (`[keychain]` extra):**
- `KeychainTokenStore` uses `keyring.set_password("broomva-health", f"{source.value}.{profile}", base64_bundle)`.
- Same `TokenBundle` model; only the storage backend changes.

---

## No PII in logs

A hard invariant. The formatter layer (`cli/formatters.py`) is the **only** place user-visible output is rendered, and it routes Pydantic models through `model_dump(mode="json")`. To prevent PII leakage:

| What | Where | Policy |
|---|---|---|
| Email | `health auth login`, login flow | Echoed once at prompt-time; never logged |
| Password | `health auth login` | Read via `getpass`; never echoed; never logged |
| MFA code | `health auth login` | Read via `getpass` or `BROOMVA_HEALTH_MFA_CODE` env; consumed once; never logged |
| Token bytes | `TokenBundle.raw_bytes` | Never formatted; the bundle's `repr` redacts |
| Sample values (HR, weight, etc.) | `health context`, `health daily-note` | Surfaced **only** when the user explicitly asks (`--format` flag); never logged in error messages |
| Device serial | `Device.hardware_id` | Surfaced under `--format` but not in error messages |
| Source-specific user IDs | `metadata` blob on samples | Stays in the trace DB; never echoed in CLI default output |

Conversation logs (per the workspace's P1 Bridge) capture agent prose but **not** the contents of tool outputs by default. Health-skill tool outputs containing values are NOT auto-promoted to the knowledge graph — see [validation-evidence.md](validation-evidence.md) §promotion-rules.

---

## No telemetry

The Health skill makes network calls **only** to the source vendor's own API. There is:

- No usage telemetry
- No crash reporter
- No analytics
- No "first run" phone-home
- No version-update check (if a check ships in v2 it'll be opt-in)

This is verified by inspection of the dependency tree. The runtime deps:
- `pydantic`, `pydantic-settings` — no network
- `typer`, `rich` — no network
- `platformdirs` — pure path discovery
- `python-garminconnect` — calls Garmin Connect only
- (optional) `pysqlcipher3` — no network
- (optional) `keyring` — system Keychain only

A future v2 dependency that phones home would be a P20 (Cross-Review) blocker.

---

## Verifying it

The `health doctor` command verifies the privacy invariants on demand:

```bash
$ health doctor
✓ ~/.config/broomva-health/ exists
✓ ~/.config/broomva-health/tokens/ permissions: 0o700
✓ Token files permissions: all 0o600 (3 of 3)
✓ Trace DB path: ~/broomva/health/traces/ (not inside iCloud)
✓ encrypt_db: false (v1 default; install [encrypted] extra for SQLCipher)
✓ No network calls in last 24h other than to source vendors (1 to connect.garmin.com)
```

The last check reads from a local rate-limiter log (which records *call destinations*, not *call contents*). If a different host appears, it's a P20-class break.

---

## What this is NOT

- **NOT HIPAA-compliant.** HIPAA applies to Covered Entities (healthcare providers + their business associates). A personal knowledge graph is not a CE. If you want HIPAA, use `apps/healthOS/` (the platform path), not this skill (the substrate path).
- **NOT GDPR-DPO-grade.** Same reason — this is personal use, not data processing on behalf of others.
- **NOT a research-grade dataset substrate.** Sample provenance is preserved, but the trace DB has no IRB-grade audit trail, no consent-form management, no participant identifiers.

For all three, the right answer is the Health platform (`apps/healthOS/`), not the Health skill (`skills/Health/`). The skill's job is to be your personal substrate, well-encrypted, never leaked.

---

## References

- Apple HealthKit privacy: https://developer.apple.com/documentation/healthkit/protecting_user_privacy
- Apple iCloud security overview: https://support.apple.com/en-us/HT202303
- SQLCipher: https://www.zetetic.net/sqlcipher/
- `pysqlcipher3`: https://pypi.org/project/pysqlcipher3/
- `keyring`: https://github.com/jaraco/keyring
- Freedesktop Secret Service: https://specifications.freedesktop.org/secret-service/latest/
- macOS Keychain Services: https://developer.apple.com/documentation/security/keychain_services
- Workspace CLAUDE.md "Projects stay on local disk (never inside iCloud)" rule
