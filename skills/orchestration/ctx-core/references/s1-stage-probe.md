# Which hook stages can inject: the 2026-09-30 probe

The System 1 gate injects through `hookSpecificOutput.additionalContext`. The
stage list in workspace#840 §6.2 was checked against the Claude Code hooks
reference (read 2026-09-30, `code.claude.com/docs/en/hooks.md`) and against one
live probe on the CLI this machine runs (2.1.280, model haiku, a jailed HOME,
`--setting-sources project`, one `--settings` file).

## Method

One probe hook was registered on every stage. It logged its input keys and
printed a JSON `additionalContext` carrying a random nonce
(`PRB-<EVENT>-<detail>-<4 digits>`). Three turns ran against one session:

1. a prompt that made the model Read, Grep, Glob, run Bash, Edit, Write, and
   start an `Explore` subagent that was asked to quote any nonce it could see;
2. `--resume <id> -p /compact`;
3. `--resume <id>` asking for every nonce visible after the compaction.

A nonce the model quotes verbatim reached it (the digits are random). The
transcript's `hook_additional_context` attachments were read as well.

## Result

| Stage | Fired | Injects | Evidence |
|---|---|---|---|
| SessionStart `startup`, `resume` | yes | yes | nonce quoted; `hook_additional_context` record |
| SessionStart `compact` | yes | yes | nonce quoted after compaction; the documented re-injection point |
| UserPromptSubmit | yes | yes | nonce quoted |
| PreToolUse `Edit`, `Write` | yes | yes | both nonces quoted |
| PostToolUse `Read`, `Bash` | yes | yes | nonces quoted |
| SubagentStart | yes | yes, into the subagent | the subagent quoted its own nonce; the parent did not see it |
| PostToolUse inside a subagent | yes | yes, into the subagent | input carries `agent_id` and `agent_type` |
| PreCompact | yes | **no** | the CLI rejects the output: `Hook JSON output validation failed — hookSpecificOutput.hookEventName: expected one of "PreToolUse" \| "UserPromptSubmit" \| ...`. No `hook_additional_context` record. The model saw the nonce only because `/compact`'s own stdout echoed the failing hook's output as an error |
| PostCompact | yes | **no** | the same validation failure; its input carries `compact_summary` |
| PostToolUse `Grep`, `Glob`; PreToolUse `MultiEdit` | **no** | — | not in this CLI's tool list (the `init` event lists `Read`, `Edit`, `Write`, `Bash`, `NotebookEdit`, and no `Grep`, `Glob` or `MultiEdit`). The model ran grep and find through Bash |

The reference agrees: its decision-control table lists PreCompact under
"top-level `decision`" only, and PostCompact under "no decision control".

## What the gate does with this

- Compaction re-injection runs on SessionStart with `source: compact`, as the
  spec says. PreCompact and PostCompact inject nothing. The gate's
  `post-compact` stage only logs which already-injected claim ids the
  `compact_summary` kept (measurement, per the spec).
- The `post-read` matcher is `Read|Grep|Glob` for forward compatibility; on
  2.1.280 only `Read` fires it. Reads made through Bash (`cat`, `sed -n`,
  `head`, `rg`) are keyed by the `post-bash` stage instead.
- `pre-edit` matches `Edit|Write|MultiEdit|NotebookEdit`; `MultiEdit` never
  fires on 2.1.280.
- Tool stages abstain inside subagents (the input has `agent_id`): the replay
  population is main transcripts, and a reviewer subagent must not be biased
  by the parent's claims. `SubagentStart` excludes reviewer agent types by name.
