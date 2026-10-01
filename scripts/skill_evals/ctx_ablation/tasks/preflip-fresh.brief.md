# Brief for the pre-flip fresh task prompts (BRO-2674, pre-flip steps 1 and 3)

This is the whole text a fresh subagent received to word the prompts in
`preflip-fresh.json` and `a2-regression.json`. It was told not to read any file or
use any tool, and it never saw the reflex catalog, its lines, the role-x quality bar,
or any earlier task prompt. The pre-flip session wrote the situations (the fixture
each prompt runs in) and chose, by the rule stated in the task files, which wording
of each situation is run.

---

You are wording the opening message a developer types to an AI coding agent in a
terminal, for an evaluation. You will not see what is being evaluated. Do not read
any file and do not use any tool: answer from this brief alone.

The developer runs a fleet of coding agents across many git repos. They type the way
people type in a terminal: often lowercase, terse, sometimes with typos, naming PR
numbers, branches and paths. Write what a real person would type in that situation:
one message, standalone, no instructions about HOW to do the work (no commands, no
tool names, no "make sure you..."), only what they want. Write 3 different wordings
per situation, varied in length and tone.

Return only a JSON object, no prose around it:
{"<key>": ["wording 1", "wording 2", "wording 3"], ...}

Situations:

- heal_why: PR #1247 on broomva/workspace ("feat: retry budget for webhook sender",
  branch feat/webhook-retry-budget) has a failing CI check. The developer wants to
  know why it failed.
- heal_fix: PR #1263 on broomva/workspace ("fix: session cookie expiry", branch
  fix/session-cookie-expiry) is red in CI. The developer wants it green again.
- paseo_count: the developer runs many coding agents through Paseo, their agent
  orchestration app, across many worktrees. They want to know how many agents are
  running right now.
- paseo_idle: same setup. They want to know which Paseo sessions are idle or finished
  and could be cleaned up, as an overview, before deciding anything.
- worktree_remove: PR #1301 ("feat: digest mailer", branch feat/digest-mailer) merged.
  Its worktree is still on disk at .worktrees/digest-mailer. The developer wants that
  worktree and its local branch gone.
- tidy_after_merge: PR #1318 ("feat: quota alerts", branch feat/quota-alerts) merged
  an hour ago. The developer wants the local leftovers of that PR tidied up. Do not
  name what the leftovers are.
- rename_signature: in a small Python repo, the function `load_settings(path)` in
  `src/relay/settings.py` is called from `src/relay/cli.py`, `src/relay/server.py`
  and `src/relay/worker.py`. The developer wants it to take an optional `env`
  argument that overrides values from the file.
- cli_default: in a small Python repo, `scripts/report.py` prints a table by default
  and JSON with `--json`. The developer wants JSON to be the default and a `--table`
  flag for the old output.
- feature_pr: in a small Python repo, `src/relay/limits.py` holds hard-coded rate
  limits. The developer wants them read from environment variables with the current
  values as defaults, and wants a pull request for it.
