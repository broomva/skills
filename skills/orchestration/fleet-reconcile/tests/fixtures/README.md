# Captured fixtures

`cc-<version>/` holds copies of every surface fleet-reconcile parses, captured
on the owner's machine by `tests/capture_fixtures.py` and anonymized (this repo
is public). `cc-2.1.280/` is the full scenario capture the behavioural tests
run on. `cc-<parsers.PINNED_CC_VERSION>/` holds only the Claude Code surfaces
(`claude/` and `meta.json`) captured on the pinned version, which must parse
with no drift; its other surfaces were not committed, because no test reads
them and each one is more anonymized data in a public repo. The job file
capture is an allowlist: keys Claude Code added after 2.1.280 (`intent`,
`linkScanPath`, `tokens` and others on 2.1.295) are dropped, since no parser
reads them.

| Path | Surface | Read by |
|---|---|---|
| `claude/version.txt` | `claude --version` | `parsers.cc_version` |
| `claude/agents.json` | `claude agents --json --all` | `parsers.parse_listing` |
| `claude/jobs/<id>/state.json` | `~/.claude/jobs/<id>/state.json` | `parsers.parse_job_state` |
| `claude/transcripts.json` | `{session id: {mtime, sub}}` from `~/.claude/projects` | `FixtureSources.transcript_index` |
| `paseo/agents/<project>/<id>.json` | `~/.paseo/agents` (a FAKE bearer planted where the real one lives) | `parsers.parse_paseo_record` |
| `paseo/schedules/<id>.json` | `~/.paseo/schedules` | `parsers.parse_schedule` |
| `gh/<owner>__<name>/{default_branch.txt,rules.json,prs.json}` | `gh api repos/<r>`, `rules/branches/<b>`, `gh pr list` | `parsers.parse_rules`, `evaluate_rules`, `parse_pr_list` |
| `launchd/<label>.json`, `<label>.print.txt` | the plist via `plutil -convert json`, and `launchctl print` | `scheduled.launchd_items`, `parsers.parse_launchctl_print` |
| `ctx/<scope>/events.jsonl` | ctx-core's event log | `observe` (the board) |
| `meta.json` | capture time and version | tests |

Paths are templates (`{HOME}/broomva`, `{HOME}/client/sri`,
`{HOME}/wt/<scope>-<n>`, `{HOME}/gone/<n>`); `tests/conftest.py` builds repos
that match them in a scratch HOME. `FixtureSources` reads a directory laid out
this way in place of the machine.
