# omnivoice

Agent skill for [OmniVoice Studio](https://github.com/debpalash/OmniVoice-Studio) — the open-source ElevenLabs alternative. Gives Claude Code, Cursor, OpenClaw, Codex, and other compatible agents the context they need to call OmniVoice's local MCP server: text-to-speech, voice cloning, voice design, and dub-pipeline primitives across 646 languages without sending any audio to the cloud.

## Install

Add the skill to your agent (Vercel-Labs [`skills`](https://www.npmjs.com/package/skills) CLI):

```bash
npx skills add broomva/skills --skill omnivoice
```

Then install OmniVoice Studio itself somewhere on your machine and wire the MCP server. The skill's `references/mcp-setup.md` walks through the wiring; the short version is:

```bash
# Pick any location; the helper scripts default to ~/OmniVoice-Studio.
export OMNIVOICE_HOME="${HOME}/OmniVoice-Studio"
git clone https://github.com/debpalash/OmniVoice-Studio.git "$OMNIVOICE_HOME"
cd "$OMNIVOICE_HOME"
uv sync
VIRTUAL_ENV="$(pwd)/.venv" uv pip install 'mcp[cli]'
```

Add to your MCP client config (e.g. `~/.claude.json`):

```json
{
  "mcpServers": {
    "omnivoice": {
      "type": "stdio",
      "command": "uv",
      "args": [
        "--directory", "<OMNIVOICE_HOME>",
        "run", "python", "-m", "backend.mcp_server"
      ],
      "env": { "OMNIVOICE_API_URL": "http://localhost:3900" }
    }
  }
}
```

Restart the agent. The skill's helper scripts (`scripts/start-backend.sh`, `scripts/check-health.sh`, `scripts/stop-backend.sh`) manage the FastAPI backend lifecycle.

> If you see `TypeError: FastMCP.__init__() got an unexpected keyword argument 'version'` on first launch, your OmniVoice Studio checkout pre-dates [debpalash/OmniVoice-Studio#112](https://github.com/debpalash/OmniVoice-Studio/pull/112). Apply that 3-line patch or wait for it to merge.

## What this skill provides

| Surface | Detail |
|---|---|
| MCP tools | `generate_speech`, `list_voices`, `list_personalities`, `list_languages`, `check_health` |
| MCP resources | `voice://{profile_id}`, `history://recent` |
| Workflows | One-shot synthesis, voice clone via saved profile, voice design via `instruct`, multilingual narration, batch audio for content pipelines |
| Decision rule | When to pick OmniVoice vs kokoro / Voicebox / Edge TTS / ElevenLabs / cloud APIs ([`references/engines-comparison.md`](references/engines-comparison.md)) |
| Lifecycle | Backend start / health / stop scripts, idempotent, port-collision-safe |
| Troubleshooting | Common failure modes + fixes ([`references/mcp-setup.md`](references/mcp-setup.md)) |

## Layout

```
omnivoice/
├── SKILL.md                              # YAML frontmatter + workflows + decision rule
├── references/
│   ├── engines-comparison.md             # When to pick OmniVoice vs other TTS engines
│   └── mcp-setup.md                      # MCP wiring, lifecycle, env vars, troubleshooting
└── scripts/
    ├── check-health.sh                   # curl /health, exit 0/1
    ├── start-backend.sh                  # idempotent uvicorn boot + 60s health probe
    └── stop-backend.sh                   # graceful SIGTERM on bound PID
```

Conforms to Anthropic's [skill-creator](https://github.com/anthropics/skills/tree/main/skill-creator) conventions. Validates clean against `quick_validate.py`.

## Two install paths

There are two ways to land this skill in your agent:

1. **Monorepo (this repo)** — `npx skills add broomva/skills --skill omnivoice`. Independent of OmniVoice Studio's release cadence; updated here on its own schedule.
2. **Bundled in OmniVoice Studio** — once [debpalash/OmniVoice-Studio#113](https://github.com/debpalash/OmniVoice-Studio/pull/113) merges, `npx skills add debpalash/OmniVoice-Studio` will install the same skill from inside OmniVoice's repo at `.claude/skills/omnivoice/`.

Both paths produce the same tool surface; the standalone exists so you can adopt the skill without waiting for OmniVoice's upstream PRs to merge.

## License

MIT — see [LICENSE](LICENSE). OmniVoice Studio itself is FSL-1.1-ALv2 (free for personal/internal use; converts to Apache-2.0 two years after each release).
