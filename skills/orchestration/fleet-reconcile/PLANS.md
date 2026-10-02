# PLANS — fleet-reconcile pre-live (BRO-2755, BRO-2756)

Branch `fix/fleet-prelive-2755-2756` off skills main 337c9d1 (skills#263 merged).
Both tickets are phase-3 preconditions; nothing is live today (both scopes
`dry_run: 1`, mode report). Parent BRO-2714.

## BRO-2755 — keychain exposure of a sandboxed driver  [DONE: measured]

Measured 2026-10-02 on the arm-D driver profile (fleet-reconcile 0.4.0), CC 2.1.280.
Evidence (machine-local): `~/.config/broomva/fleet/credential-drill-20261001/keychain-table-20261002-bro2755.md`.
- securityd is reachable from inside the driver sandbox (throwaway-keychain decoy `readable`).
- A `denyRead` on the keychain FILE is effective but whole-file (blocks gh too).
- Only a `com.apple.SecurityServer` mach-lookup deny closes it otherwise; not expressible via `--settings`.
- Tighten now (profile.py): denyRead the credential files the gh route doesn't need.
- Report W1 options (D accept / A env-token+file-deny / mach-deny-unavailable). Owner decides, not us.

## BRO-2756 — #263 review MINORs (18 items). Fix w/ test, or close w/ reason.

1. broken state dir alerts hourly w/ wrong reason → own alert kind `statedir`, stamp under TMPDIR. (tick.sh)
2. fallback /dev/null branch → capture output in memory when mktemp fails; test. (tick.sh)
3. `_dry()` forces dry silently → say why on stderr. (fleet_reconcile cmd_act_verb)
4. "every verb stays dry" only unit-tests `_dry()` → CLI-level checks act label|spawn, send-gate pre, coordinator DRY_RUN. (tests)
5. two sources of truth for dryness → tick.sh asks `fleet is-dry`. (tick.sh + new CLI verb)
6. `live_accepted` free text → require it to name BRO-2755 and BRO-2756. (config.live_refusal)
7. report-mode + dry_run 0 halts whole tick → CLOSE: keep fail-closed (dry_run meaningless in report mode); document.
8. fork PRs not refused → PR_FIELDS += isCrossRepository; driver_check refuses forks (W3). (parsers, act)
9. open-ask item logs Stuck/error every tick → rate-limit (ledger notice kind + transition gate). (fleet_reconcile, ledger)
10. head 121–200 passes but shows clipped → cap REF_RE at 120 (`{0,119}`); length-boundary test. (common)
11. render_template blanks non-string silently → raise. (act)
12. name BRO-2756 in the live gate → SKILL.md Phase 3 + config.live_refusal. (config, SKILL)
13. docs: REF_RE comment (NBSP not space); CHANGELOG/SKILL list fuller guard refusals. (common, CHANGELOG, SKILL)
14. repo slug in brief not guard-checked → spawn refuses a withheld slug (crm). (act)
15. split branch-name cases out of test_a_spawn_is_refused_for_a_held_draft_or_dependabot_pr. (tests)
16. driver brief LFS: fetch base first; "after your last commit"; Never-push-before-LFS; accurate BLOCKED reason. (template)
17. pin "Before every push"/"without pushing" in brief test. (tests)
18. CHANGELOG: 0.4.0 note still says old push/LFS order; add reorder entry. (CHANGELOG)

## Verify
- `make test` (pytest) green; mutation_check.py; shellcheck tick.sh.
- PR links both tickets; cross-review (P20) + p9 in foreground; merge pinned on green.

## Do NOT
touch ~/.config/ctx/fleet.json; set dry_run 0 / live_accepted; reinstall launchd;
edit settings.json/.control/policy.yaml/CLAUDE.md/AGENTS.md. Use trash not rm -rf.

## Status (2026-10-02)
All 18 BRO-2756 findings fixed with tests, or closed with a reason (#7: kept
fail-closed scope-wide — dry_run 0 is meaningless in report mode and declaring
it is a misconfiguration to catch; documented in config.live_refusal). BRO-2755
measured and the profile tightened; W1 options recorded for the owner. Full
pytest suite green; 18 new/changed mutants all killed; shellcheck clean. Next:
PR, cross-review (P20), p9, merge pinned.
