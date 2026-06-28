# Install

```bash
npx skills add broomva/dogfood
```

That's it — the skill is now available as `/dogfood` in any Claude Code session in this workspace.

## Verify

After install, in a fresh session:

```
/dogfood plan
```

Expected output: a six-row Dogfood Plan keyed to the detected tech stack, citing the bstack cookbook entry. If the stack is `unknown`, the agent will state so explicitly and ask you to declare it.

## Bstack dependency

This skill inherits the per-stack cookbook from [`broomva/bstack`](https://github.com/broomva/bstack). The cookbook lives at `bstack/references/dogfood-patterns.md` and is the canonical source for the per-stack interaction surfaces matrix.

If you don't have bstack installed:

```bash
npx skills add broomva/bstack
```

bstack also ships `bstack doctor §13` which auto-detects your tech stack and reports dogfood-readiness — pairs cleanly with this skill but is not required (the skill detects independently).

## Update

```bash
npx skills update broomva/dogfood
```

## Uninstall

```bash
npx skills remove broomva/dogfood
```
