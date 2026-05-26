#!/usr/bin/env bun
/**
 * register-slash-commands.ts — Register/update slash commands without running the full daemon
 *
 * Useful for one-time setup or updating command definitions after changes.
 *
 * Usage:
 *   bun scripts/register-slash-commands.ts
 *   bun scripts/register-slash-commands.ts --clear   # Remove all guild commands
 */

import { REST, Routes, ApplicationCommandType, ApplicationCommandOptionType } from "discord.js";
import { readFileSync, existsSync } from "fs";
import { join } from "path";
import { homedir } from "os";

// ── Config ────────────────────────────────────────────────────────────────

const DISCORD_ENV_PATH = join(homedir(), ".claude/channels/discord/.env");
const CONFIG_ENV_PATH = join(homedir(), ".claude/discord-sessions/config.env");

function readEnvValue(filePath: string, key: string): string {
  if (!existsSync(filePath)) return "";
  const content = readFileSync(filePath, "utf8");
  const match = content.match(new RegExp(`^${key}=["']?(.+?)["']?$`, "m"));
  return match?.[1] ?? "";
}

const BOT_TOKEN = readEnvValue(DISCORD_ENV_PATH, "DISCORD_BOT_TOKEN");
if (!BOT_TOKEN) {
  console.error(`FATAL: No DISCORD_BOT_TOKEN found in ${DISCORD_ENV_PATH}`);
  process.exit(1);
}

const GUILD_ID = readEnvValue(CONFIG_ENV_PATH, "DISCORD_GUILD_ID");
if (!GUILD_ID) {
  console.error(`FATAL: No DISCORD_GUILD_ID found in ${CONFIG_ENV_PATH}`);
  process.exit(1);
}

// ── Command Definitions ───────────────────────────────────────────────────

const SLASH_COMMANDS = [
  {
    name: "session",
    description: "Manage the Claude Code session for this channel",
    type: ApplicationCommandType.ChatInput,
    options: [
      {
        name: "status",
        description: "Show session info (workdir, uptime, name) for this channel",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "restart",
        description: "Kill and respawn the session",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "fresh",
            description: "Start a clean conversation (new session ID)",
            type: ApplicationCommandOptionType.Boolean,
            required: false,
          },
        ],
      },
      {
        name: "refresh",
        description:
          "Kill and respawn with same session-id (picks up new skills/CLAUDE.md)",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "kill",
        description: "Kill the session",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "wake",
        description: "Wake a suspended session",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "workdir",
        description: "Show or change the session's working directory",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "path",
            description: "New working directory (leave empty to show current)",
            type: ApplicationCommandOptionType.String,
            required: false,
            autocomplete: true,
          },
        ],
      },
      {
        name: "watch",
        description: "Stream agent activity to this channel (toggle on/off)",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "mode",
            description: "Display mode (default: live)",
            type: ApplicationCommandOptionType.String,
            required: false,
            choices: [
              { name: "live — updating snapshot of current state", value: "live" },
              { name: "log — timestamped history of all activity", value: "log" },
            ],
          },
        ],
      },
      {
        name: "snapshot",
        description: "Current pane view as a scrollable text file",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "history",
        description: "Full session scrollback (entire conversation) as a text file",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "send",
        description: "Send a keypress or text to the session (for prompts, approvals, feedback)",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "input",
            description: "Text to send, or a key: yes, no, esc, enter, tab, up, down, 1, 2, 3",
            type: ApplicationCommandOptionType.String,
            required: true,
            autocomplete: true,
          },
        ],
      },
      {
        name: "profile",
        description: "Show or switch the auth profile for this channel",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "name",
            description: "Profile to switch to (leave empty to show current)",
            type: ApplicationCommandOptionType.String,
            required: false,
            autocomplete: true,
          },
        ],
      },
    ],
  },
  {
    name: "skills",
    description: "Manage skills for this channel's Claude session",
    type: ApplicationCommandType.ChatInput,
    options: [
      {
        name: "list",
        description: "List installed skills for this channel's session",
        type: ApplicationCommandOptionType.Subcommand,
      },
      {
        name: "install",
        description: "Install a skill (runs npx skills add in the session)",
        type: ApplicationCommandOptionType.Subcommand,
        options: [
          {
            name: "name",
            description: "Skill name to install",
            type: ApplicationCommandOptionType.String,
            required: true,
          },
        ],
      },
    ],
  },
  {
    name: "discover",
    description: "Trigger channel/thread discovery",
    type: ApplicationCommandType.ChatInput,
  },
  {
    name: "ask",
    description: "Send a prompt to the channel's Claude session",
    type: ApplicationCommandType.ChatInput,
    options: [
      {
        name: "prompt",
        description: "The prompt to send",
        type: ApplicationCommandOptionType.String,
        required: true,
      },
    ],
  },
  {
    name: "run",
    description: "Run a Claude Code skill (slash command) in this channel's session",
    type: ApplicationCommandType.ChatInput,
    options: [
      {
        name: "skill",
        description: "Skill name (e.g. commit, review-pr, ship)",
        type: ApplicationCommandOptionType.String,
        required: true,
        autocomplete: true,
      },
      {
        name: "args",
        description: "Optional arguments to pass to the skill",
        type: ApplicationCommandOptionType.String,
        required: false,
      },
    ],
  },
];

// ── Main ──────────────────────────────────────────────────────────────────

async function main() {
  const rest = new REST({ version: "10" }).setToken(BOT_TOKEN);

  // Fetch application ID
  console.log("Fetching application ID...");
  const app = (await rest.get(Routes.oauth2CurrentApplication())) as {
    id: string;
    name: string;
  };
  const appId = app.id;
  console.log(`Application: ${app.name} (${appId})`);
  console.log(`Guild: ${GUILD_ID}`);

  const clearMode = process.argv.includes("--clear");

  if (clearMode) {
    console.log("\nClearing all guild commands...");
    await rest.put(Routes.applicationGuildCommands(appId, GUILD_ID), {
      body: [],
    });
    console.log("All guild commands cleared.");
    return;
  }

  console.log(`\nRegistering ${SLASH_COMMANDS.length} commands...`);

  const result = await rest.put(
    Routes.applicationGuildCommands(appId, GUILD_ID),
    { body: SLASH_COMMANDS }
  );

  const commands = result as Array<{ name: string; id: string }>;
  console.log("\nRegistered commands:");
  for (const cmd of commands) {
    console.log(`  /${cmd.name} (${cmd.id})`);
  }

  console.log("\nDone. Commands are available immediately in the guild.");
}

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
