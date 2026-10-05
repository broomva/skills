# mod-anything

An [Agent Skill](https://agentskills.io/specification) for changing or extending software or
a device you own but whose source you don't control: a desktop app, a website, a game, a
device protocol, a CLI. The agent picks the cheapest route that reaches the idea, checks its
work against the running original, keeps a journal, and ends every run with a field note the
next agent can search.

The method generalizes the `mod-any-game` skill from
[rehan-remade/universal-modder](https://github.com/rehan-remade/universal-modder) (MIT, see
[NOTICE](NOTICE)) beyond games.

## Install

```bash
npx skills add broomva/skills --skill mod-anything
```

It works with any agent that reads `SKILL.md` and can run shell commands (Claude Code, Codex,
Cursor, Gemini CLI and others). `SKILL.md` is what the agent reads; this file is for people.

## What it does

1. **Intake and recon.** The target, its exact version, the idea in one sentence, and what
   it is built on. `scripts/recon_macos_app.py <App> --json` does this for macOS apps.
2. **Pick a rung** on the route ladder, cheapest first: data and config, sanctioned API,
   patch from inside, hooks and wires, reimplement. The choice and its reason go in the
   journal before any code is written.
3. **Work in a lab**, never in your real profile: a separate profile, a copy of the vault,
   a mock keychain. The skill lists what a lab does not isolate.
4. **Verify in the running target.** Every verified step has an evidence file, and the
   journal refuses a step without one.
5. **Stall breaker.** The third identical failure on a route exits 3 with a checklist: re-check
   the rules, then re-rank, starting with "can the original simply be run?".
6. **Field note and publish check.** The mod and its note are assembled in a ship tree, linted,
   and run through a fail-closed filter before anything is shared.

## Safety rules

These are hard rules in `SKILL.md`, with reasons in
[references/envelope.md](references/envelope.md):

- You must have the right to modify the target. Apps whose terms forbid client mods are out of
  scope.
- Never defeat a protection: integrity checks, anti-cheat or anti-automation, licence or DRM
  checks, access controls.
- Bring your own files: never ship the target's bytes, decompiled code or extracted assets.
- The agent asks before it drives your input, installs into your real profile, connects to a
  device, writes to a live service, uses your signed-in session, deletes anything or
  publishes.
- Vulnerabilities found along the way follow coordinated disclosure.

## Scripts

All three are Python 3.9+, standard library only, and print `--help`.

| Script | Purpose | Exit codes |
|---|---|---|
| `scripts/modlog.py` | journal, route record, stall breaker, field-note scaffold and lint | 0 ok · 1 lint findings · 2 refused or unreadable · 3 stall |
| `scripts/publish_check.py` | fail-closed filter before sharing (allowlisted file types, secrets via gitleaks, home paths, hardware addresses, deny-file terms); `--json` available | 0 clean · 1 findings · 2 could not read |
| `scripts/recon_macos_app.py` | recon of a macOS `.app` bundle with ranked routes | 0 ok · 2 not an app bundle |

`publish_check.py` is a filter in front of a person, not a privacy guarantee. It decodes
nothing and does not detect cookies, sessions or personal data; its `--help` and its OK line
say so. The agent runs it, and the user reviews its REVIEW list before anything is published.

## Layout

```
SKILL.md          the procedure the agent follows
references/       the ladder, the envelope, the field-note format, playbooks
scripts/          modlog.py, publish_check.py, recon_macos_app.py
tests/            pytest suites for the three scripts
examples/         recon output for three apps; a worked Obsidian plugin with its lab
field-notes/      notes from real runs, searched before a new run starts
```

## Development

```bash
python -m pytest tests/ -q          # needs pytest; gitleaks on PATH enables its tests
```

CI (`.github/workflows/test-mod-anything.yml`) runs the tests on Python 3.9, 3.11 and 3.12
with gitleaks installed. It also checks the stall exit code, lints the field notes, and runs
the publish check over the shipped examples.

## License

MIT, as the rest of this repository. Attribution for the method is in [NOTICE](NOTICE).
