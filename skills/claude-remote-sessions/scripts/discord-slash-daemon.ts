#!/usr/bin/env bun
/**
 * discord-slash-daemon.ts — Discord slash command daemon for Claude Remote Sessions
 *
 * A single Bun process that registers and handles slash commands, bridging them
 * to the tmux-managed Claude Code sessions via discord-session-manager.sh.
 *
 * Startup:
 *   bun scripts/discord-slash-daemon.ts
 *
 * Or via watchdog (auto-managed in dc-slash-daemon tmux session).
 */

import {
  Client,
  GatewayIntentBits,
  REST,
  Routes,
  EmbedBuilder,
  AttachmentBuilder,
  InteractionType,
  ApplicationCommandType,
  ApplicationCommandOptionType,
  type ChatInputCommandInteraction,
  type AutocompleteInteraction,
} from "discord.js";
import { readFileSync, writeFileSync, existsSync, readdirSync, statSync } from "fs";
import { join } from "path";
import { homedir } from "os";
import { $ } from "bun";

// ── Config ────────────────────────────────────────────────────────────────

const DISCORD_ENV_PATH = join(homedir(), ".claude/channels/discord/.env");
const CONFIG_ENV_PATH = join(homedir(), ".claude/discord-sessions/config.env");
const SESSIONS_DIR = join(homedir(), ".claude/discord-sessions");
const SESSIONS_REGISTRY = join(SESSIONS_DIR, "sessions.json");
const WORKDIR_MAP_PATH = join(SESSIONS_DIR, "workdir-map.json");
const MANAGER_PATH = join(import.meta.dir, "discord-session-manager.sh");

function readEnvValue(filePath: string, key: string): string {
  if (!existsSync(filePath)) return "";
  const content = readFileSync(filePath, "utf8");
  const match = content.match(new RegExp(`^${key}=["']?(.+?)["']?$`, "m"));
  return match?.[1] ?? "";
}

const BOT_TOKEN = readEnvValue(DISCORD_ENV_PATH, "DISCORD_BOT_TOKEN");
if (!BOT_TOKEN) {
  console.error(
    `[slash-daemon] FATAL: No DISCORD_BOT_TOKEN found in ${DISCORD_ENV_PATH}`
  );
  console.error("Run: /discord:configure <token> first");
  process.exit(1);
}

const GUILD_ID = readEnvValue(CONFIG_ENV_PATH, "DISCORD_GUILD_ID");
if (!GUILD_ID) {
  console.error(
    `[slash-daemon] FATAL: No DISCORD_GUILD_ID found in ${CONFIG_ENV_PATH}`
  );
  process.exit(1);
}

// ── Helpers ───────────────────────────────────────────────────────────────

function readSessionsRegistry(): Record<
  string,
  {
    type: string;
    name: string;
    tmux: string;
    parent: string | null;
    created: string;
  }
> {
  try {
    if (!existsSync(SESSIONS_REGISTRY)) return {};
    return JSON.parse(readFileSync(SESSIONS_REGISTRY, "utf8"));
  } catch {
    return {};
  }
}

function readWorkdirMap(): Record<string, string> {
  try {
    if (!existsSync(WORKDIR_MAP_PATH)) return {};
    return JSON.parse(readFileSync(WORKDIR_MAP_PATH, "utf8"));
  } catch {
    return {};
  }
}

function findSessionByChannel(
  channelId: string
): {
  id: string;
  type: string;
  name: string;
  tmux: string;
  parent: string | null;
  created: string;
} | null {
  const registry = readSessionsRegistry();
  if (registry[channelId]) {
    return { id: channelId, ...registry[channelId] };
  }
  return null;
}

async function isTmuxAlive(sessionName: string): Promise<boolean> {
  try {
    const result = await $`tmux has-session -t ${sessionName} 2>/dev/null`.nothrow().quiet();
    return result.exitCode === 0;
  } catch {
    return false;
  }
}

async function readWorkdir(channelId: string): Promise<string> {
  const wdFile = join(SESSIONS_DIR, channelId, ".workdir");
  try {
    if (existsSync(wdFile)) return readFileSync(wdFile, "utf8").trim();
  } catch {}
  return "(unknown)";
}

async function readSessionId(channelId: string): Promise<string> {
  const sidFile = join(SESSIONS_DIR, channelId, ".session-id");
  try {
    if (existsSync(sidFile)) return readFileSync(sidFile, "utf8").trim();
  } catch {}
  return "(none)";
}

function readProfile(channelId: string): string {
  const profileFile = join(SESSIONS_DIR, channelId, ".profile");
  try {
    if (existsSync(profileFile)) return readFileSync(profileFile, "utf8").trim();
  } catch {}
  return "default";
}

async function runManager(...args: string[]): Promise<string> {
  const result = await $`bash ${MANAGER_PATH} ${args}`.nothrow().quiet();
  const out = result.stdout?.toString()?.trim();
  const err = result.stderr?.toString()?.trim();
  return out || err || (result.exitCode === 0 ? "OK" : "Command failed");
}

function escapeForTmux(input: string): string {
  // Escape single quotes and newlines for tmux send-keys
  return input
    .replace(/'/g, "'\\''")
    .replace(/\n/g, " ")
    .replace(/\r/g, "");
}

function formatUptime(createdIso: string): string {
  try {
    const created = new Date(createdIso);
    const now = new Date();
    const diffMs = now.getTime() - created.getTime();
    const hours = Math.floor(diffMs / 3600000);
    const minutes = Math.floor((diffMs % 3600000) / 60000);
    if (hours > 24) {
      const days = Math.floor(hours / 24);
      return `${days}d ${hours % 24}h`;
    }
    return `${hours}h ${minutes}m`;
  } catch {
    return "unknown";
  }
}

function extractSkillDescription(skillMdPath: string, fallback: string): string {
  try {
    const content = readFileSync(skillMdPath, "utf8");
    const descMatch = content.match(
      /^description:\s*>?\s*\n?\s*(.+?)(?:\n\S|\n---)/ms
    );
    return descMatch
      ? descMatch[1].replace(/\n\s*/g, " ").trim().slice(0, 90)
      : fallback;
  } catch {
    return fallback;
  }
}

function scanAvailableSkills(): Array<{ name: string; description: string }> {
  const skills: Map<string, string> = new Map();

  // 1. User-installed skills (~/.claude/skills/ and ~/.agents/skills/)
  const userSkillDirs = [
    join(homedir(), ".claude/skills"),
    join(homedir(), ".agents/skills"),
  ];

  for (const dir of userSkillDirs) {
    if (!existsSync(dir)) continue;
    try {
      for (const entry of readdirSync(dir)) {
        if (skills.has(entry)) continue;
        const skillMd = join(dir, entry, "SKILL.md");
        if (!existsSync(skillMd)) continue;
        skills.set(entry, extractSkillDescription(skillMd, entry));
      }
    } catch {}
  }

  // 2. Plugin skills (~/.claude/plugins/installed_plugins.json → each plugin's skills/)
  const installedPluginsPath = join(
    homedir(),
    ".claude/plugins/installed_plugins.json"
  );
  if (existsSync(installedPluginsPath)) {
    try {
      const pluginsData = JSON.parse(
        readFileSync(installedPluginsPath, "utf8")
      );
      const plugins = pluginsData?.plugins ?? {};

      for (const [pluginKey, installs] of Object.entries(plugins)) {
        const installArr = installs as Array<{ installPath: string }>;
        if (!installArr?.length) continue;
        const installPath = installArr[0].installPath;
        // Plugin name is the part before @marketplace (e.g., "superpowers" from "superpowers@claude-plugins-official")
        const pluginName = pluginKey.split("@")[0];
        const pluginSkillsDir = join(installPath, "skills");

        if (!existsSync(pluginSkillsDir)) continue;
        try {
          for (const entry of readdirSync(pluginSkillsDir)) {
            const skillMd = join(pluginSkillsDir, entry, "SKILL.md");
            if (!existsSync(skillMd) || !statSync(join(pluginSkillsDir, entry)).isDirectory()) continue;
            const namespacedName = `${pluginName}:${entry}`;
            if (skills.has(namespacedName)) continue;
            skills.set(
              namespacedName,
              extractSkillDescription(skillMd, entry)
            );
          }
        } catch {}
      }
    } catch {}
  }

  return Array.from(skills.entries())
    .map(([name, description]) => ({ name, description }))
    .sort((a, b) => a.name.localeCompare(b.name));
}

// Cache skills list (refresh every 5 minutes)
let _skillsCache: Array<{ name: string; description: string }> = [];
let _skillsCacheTime = 0;

function getSkillsWithCache(): Array<{ name: string; description: string }> {
  const now = Date.now();
  if (now - _skillsCacheTime > 5 * 60 * 1000 || _skillsCache.length === 0) {
    _skillsCache = scanAvailableSkills();
    _skillsCacheTime = now;
    console.log(
      `[slash-daemon] Skills cache refreshed: ${_skillsCache.length} skills`
    );
  }
  return _skillsCache;
}

// Scan project-local skills for a specific workdir
function scanProjectSkills(
  workdir: string
): Array<{ name: string; description: string }> {
  const skills: Array<{ name: string; description: string }> = [];
  const seen = new Set<string>();

  for (const subdir of [
    join(workdir, ".claude", "skills"),
    join(workdir, "skills"),
  ]) {
    if (!existsSync(subdir)) continue;
    try {
      for (const entry of readdirSync(subdir)) {
        if (seen.has(entry)) continue;
        const skillMd = join(subdir, entry, "SKILL.md");
        if (!existsSync(skillMd)) continue;
        seen.add(entry);
        skills.push({
          name: entry,
          description: extractSkillDescription(skillMd, entry),
        });
      }
    } catch {}
  }
  return skills.sort((a, b) => a.name.localeCompare(b.name));
}

// ── Slash Command Definitions ─────────────────────────────────────────────

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

// ── Command Handlers ──────────────────────────────────────────────────────

async function handleSessionStatus(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);

  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  const workdir = await readWorkdir(channelId);
  const sessionId = await readSessionId(channelId);
  const profile = readProfile(channelId);
  const uptime = formatUptime(session.created);
  const isSuspended = existsSync(
    join(SESSIONS_DIR, channelId, ".suspended")
  );

  let status = alive ? "UP" : "DOWN";
  if (isSuspended) status = "SUSPENDED";

  const embed = new EmbedBuilder()
    .setTitle(`Session: ${session.name}`)
    .setColor(alive ? 0x00ff00 : isSuspended ? 0xffaa00 : 0xff0000)
    .addFields(
      { name: "Status", value: status, inline: true },
      { name: "Type", value: session.type, inline: true },
      { name: "Profile", value: `\`${profile}\``, inline: true },
      { name: "Uptime", value: uptime, inline: true },
      { name: "tmux", value: `\`${session.tmux}\``, inline: true },
      { name: "Session ID", value: `\`${sessionId.slice(0, 8)}...\``, inline: true },
      { name: "Workdir", value: `\`${workdir}\``, inline: false }
    );

  if (session.parent) {
    embed.addFields({
      name: "Parent",
      value: `<#${session.parent}>`,
      inline: true,
    });
  }

  // Return the embed as a serialized instruction — we'll handle this specially
  return JSON.stringify({ embed: embed.toJSON() });
}

function clearSessionId(channelId: string): void {
  const sidFile = join(SESSIONS_DIR, channelId, ".session-id");
  try {
    if (existsSync(sidFile)) {
      const { unlinkSync } = require("fs");
      unlinkSync(sidFile);
    }
  } catch {}
}

async function handleSessionRestart(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const fresh = interaction.options.getBoolean("fresh") ?? false;

  // Kill existing session
  await runManager("kill", channelId);

  // Clear stale session-id lock — Claude Code doesn't release on kill
  clearSessionId(channelId);

  // Respawn
  const args = ["spawn", channelId, "--name", session.name];
  if (fresh) args.push("--fresh");

  const workdir = await readWorkdir(channelId);
  if (workdir && workdir !== "(unknown)") {
    args.push("--workdir", workdir);
  }

  const output = await runManager(...args);
  const freshNote = fresh ? " (fresh conversation)" : " (resumed conversation)";
  return `Session restarted${freshNote}\n\`\`\`\n${output}\n\`\`\``;
}

async function handleSessionRefresh(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  // Kill and respawn — picks up new skills/CLAUDE.md
  await runManager("kill", channelId);

  // Clear stale session-id lock — Claude Code doesn't release on kill
  clearSessionId(channelId);

  const args = ["spawn", channelId, "--name", session.name];
  const workdir = await readWorkdir(channelId);
  if (workdir && workdir !== "(unknown)") {
    args.push("--workdir", workdir);
  }

  const output = await runManager(...args);
  return `Session refreshed (picks up new skills/CLAUDE.md)\n\`\`\`\n${output}\n\`\`\``;
}

async function handleSessionKill(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel.";
  }

  const output = await runManager("kill", channelId);
  return `Session killed.\n\`\`\`\n${output}\n\`\`\``;
}

async function handleSessionWake(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const output = await runManager("wake", channelId);
  return `\`\`\`\n${output}\n\`\`\``;
}

async function handleSessionWorkdir(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const newPath = interaction.options.getString("path");

  if (!newPath) {
    // Show current workdir
    const workdir = await readWorkdir(channelId);
    return `Current workdir: \`${workdir}\``;
  }

  // Change workdir: kill + respawn with new workdir
  await runManager("kill", channelId);
  clearSessionId(channelId);
  const output = await runManager(
    "spawn",
    channelId,
    "--name",
    session.name,
    "--workdir",
    newPath
  );
  return `Workdir changed to \`${newPath}\`. Session respawned.\n\`\`\`\n${output}\n\`\`\``;
}

function readChannelProfiles(): Record<string, string> {
  const cpFile = join(SESSIONS_DIR, "channel-profiles.json");
  try {
    if (existsSync(cpFile)) return JSON.parse(readFileSync(cpFile, "utf8"));
  } catch {}
  return {};
}

function listAvailableProfiles(): string[] {
  const profilesFile = join(SESSIONS_DIR, "profiles.env");
  try {
    if (!existsSync(profilesFile)) return ["default"];
    const content = readFileSync(profilesFile, "utf8");
    const profiles: string[] = ["default"];
    for (const line of content.split("\n")) {
      const m = line.trim().match(/^\[(.+)\]$/);
      if (m && m[1] !== "default") profiles.push(m[1]);
    }
    return profiles;
  } catch {
    return ["default"];
  }
}

function writeChannelProfiles(profiles: Record<string, string>): void {
  const cpFile = join(SESSIONS_DIR, "channel-profiles.json");
  writeFileSync(cpFile, JSON.stringify(profiles, null, 2) + "\n");
}

async function handleSessionProfile(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const newProfile = interaction.options.getString("name");

  if (!newProfile) {
    // Show current profile and available profiles
    const current = readProfile(channelId);
    const available = listAvailableProfiles();
    return `Current profile: \`${current}\`\nAvailable: ${available.map(p => `\`${p}\``).join(", ")}\n\nUse \`/session profile name:<profile>\` to switch.`;
  }

  // Validate profile exists
  const available = listAvailableProfiles();
  if (!available.includes(newProfile)) {
    return `Profile \`${newProfile}\` not found. Available: ${available.map(p => `\`${p}\``).join(", ")}`;
  }

  // Update channel-profiles.json
  const channelProfiles = readChannelProfiles();
  channelProfiles[session.name] = newProfile;
  writeChannelProfiles(channelProfiles);

  // Kill + respawn with same session-id (preserves history)
  await runManager("kill", channelId);
  // Don't clear session-id — we want to preserve conversation history
  const output = await runManager(
    "spawn",
    channelId,
    "--name",
    session.name
  );
  return `Profile switched to \`${newProfile}\`. Session respawned with same history.\n\`\`\`\n${output}\n\`\`\``;
}

async function handleSkillsList(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const workdir = await readWorkdir(channelId);

  // Collect skills by category
  const projectSkills: string[] = [];
  const globalSkills: string[] = [];
  const pluginSkills: string[] = [];

  // 1. Project-local skills (workdir/.claude/skills/ and workdir/skills/)
  if (workdir && workdir !== "(unknown)") {
    for (const subdir of [join(workdir, ".claude", "skills"), join(workdir, "skills")]) {
      if (!existsSync(subdir)) continue;
      try {
        for (const entry of readdirSync(subdir)) {
          if (existsSync(join(subdir, entry, "SKILL.md"))) {
            if (!projectSkills.includes(entry)) projectSkills.push(entry);
          }
        }
      } catch {}
    }
  }

  // 2. Global user skills (~/.claude/skills/ and ~/.agents/skills/)
  const seen = new Set<string>();
  for (const dir of [join(homedir(), ".claude/skills"), join(homedir(), ".agents/skills")]) {
    if (!existsSync(dir)) continue;
    try {
      for (const entry of readdirSync(dir)) {
        if (seen.has(entry)) continue;
        if (existsSync(join(dir, entry, "SKILL.md"))) {
          seen.add(entry);
          globalSkills.push(entry);
        }
      }
    } catch {}
  }

  // 3. Plugin skills
  const installedPluginsPath = join(homedir(), ".claude/plugins/installed_plugins.json");
  if (existsSync(installedPluginsPath)) {
    try {
      const pluginsData = JSON.parse(readFileSync(installedPluginsPath, "utf8"));
      for (const [key, installs] of Object.entries(pluginsData?.plugins ?? {})) {
        const arr = installs as Array<{ installPath: string }>;
        if (!arr?.length) continue;
        const pluginName = key.split("@")[0];
        const sd = join(arr[0].installPath, "skills");
        if (!existsSync(sd)) continue;
        try {
          for (const entry of readdirSync(sd)) {
            if (existsSync(join(sd, entry, "SKILL.md")) && statSync(join(sd, entry)).isDirectory()) {
              pluginSkills.push(`${pluginName}:${entry}`);
            }
          }
        } catch {}
      }
    } catch {}
  }

  const total = projectSkills.length + globalSkills.length + pluginSkills.length;
  if (total === 0) {
    return "No skills found.";
  }

  const parts: string[] = [];
  if (projectSkills.length > 0) {
    parts.push(`**Project** (${projectSkills.length}): ${projectSkills.map(s => `\`${s}\``).join(", ")}`);
  }
  parts.push(`**Global** (${globalSkills.length}): ${globalSkills.length} skills installed`);
  parts.push(`**Plugins** (${pluginSkills.length}): ${[...new Set(pluginSkills.map(s => s.split(":")[0]))].map(p => `\`${p}:*\``).join(", ")}`);
  parts.push(`\nTotal: **${total}** skills | Workdir: \`${workdir}\``);
  parts.push(`Use \`/run\` with autocomplete to invoke any skill.`);

  return parts.join("\n");
}

async function handleSkillsInstall(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const skillName = interaction.options.getString("name", true);
  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running. Use \`/session wake\` or \`/session restart\` first.`;
  }

  // Send the install command to the tmux session
  const escapedCmd = escapeForTmux(`npx @anthropic-ai/claude-code skills add ${skillName} -g -y`);
  try {
    await $`tmux send-keys -t ${session.tmux} ${escapedCmd} Enter`.quiet();
  } catch (e: any) {
    return `Failed to send install command: ${e.message}`;
  }

  // Wait a bit, then refresh the session to pick up the new skill
  return `Installing skill \`${skillName}\`... Command sent to session \`${session.tmux}\`.\nUse \`/session refresh\` after installation completes to reload.`;
}

async function handleDiscover(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const output = await runManager("discover-all");
  return `Discovery complete.\n\`\`\`\n${output}\n\`\`\``;
}

async function handleAsk(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running. Use \`/session wake\` or \`/session restart\` first.`;
  }

  const prompt = interaction.options.getString("prompt", true);
  const escapedPrompt = escapeForTmux(prompt);

  try {
    await $`tmux send-keys -t ${session.tmux} ${escapedPrompt} Enter`.quiet();
  } catch (e: any) {
    return `Failed to send prompt: ${e.message}`;
  }

  // Auto-start activity watch
  startAutoWatch(channelId);

  return `Sent to session \`${session.name}\`:\n> ${prompt.length > 200 ? prompt.slice(0, 200) + "..." : prompt}`;
}

async function handleRun(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running. Use \`/session wake\` or \`/session restart\` first.`;
  }

  const skillName = interaction.options.getString("skill", true);
  const args = interaction.options.getString("args") ?? "";
  const command = `/${skillName}${args ? " " + args : ""}`;
  const escapedCmd = escapeForTmux(command);

  try {
    await $`tmux send-keys -t ${session.tmux} ${escapedCmd} Enter`.quiet();
  } catch (e: any) {
    return `Failed to send command: ${e.message}`;
  }

  // Auto-start activity watch
  startAutoWatch(channelId);

  return `Sent \`${command}\` to session \`${session.name}\``;
}

// ── Activity Watcher ─────────────────────────────────────────────────────

type WatchMode = "live" | "log";

interface WatchState {
  channelId: string;
  messageId: string;
  tmuxSession: string;
  sessionName: string;
  interval: ReturnType<typeof setInterval>;
  lastContent: string;
  lastRawLines: Set<string>;
  logBuffer: string[];
  logMessageId: string;
  mode: WatchMode;
  idleCount: number;
  startedAt: number;
}

const activeWatches: Map<string, WatchState> = new Map();

const WATCH_INTERVAL_MS = 4000;
const IDLE_STOP_COUNT = 15; // stop after ~60s of idle

function parseAgentActivity(raw: string): string {
  const lines = raw.split("\n").filter((l) => l.trim());
  const status: string[] = [];
  let isIdle = false;

  for (const line of lines) {
    const trimmed = line.trim();

    // Agent activity indicators
    if (trimmed.match(/^[●⏺]\s/)) {
      status.push(trimmed.replace(/[●⏺]\s*/, "▸ "));
    }
    // Agent tree lines
    else if (trimmed.match(/^[├└─│┊┆|]\s*─/)) {
      const cleaned = trimmed
        .replace(/[├└┊┆│]/g, "")
        .replace(/─+\s*/, "  ")
        .trim();
      if (cleaned) status.push(`  ${cleaned}`);
    }
    // Exploring/thinking indicator
    else if (trimmed.match(/^[✱✲*]\s/)) {
      status.push(trimmed.replace(/^[✱✲*]\s*/, "⟳ "));
    }
    // Task checklist
    else if (trimmed.match(/^[□■☐☑]\s/)) {
      const icon = trimmed.startsWith("■") || trimmed.startsWith("☑") ? "✓" : "○";
      status.push(`${icon} ${trimmed.replace(/^[□■☐☑]\s*/, "")}`);
    }
    // Done indicators
    else if (trimmed.match(/Done|Completed|✓/i) && trimmed.length < 80) {
      status.push(`✓ ${trimmed}`);
    }
    // Tool use lines
    else if (trimmed.match(/tool uses?|tokens/i) && trimmed.length < 100) {
      status.push(`  ${trimmed}`);
    }
    // Running N agents
    else if (trimmed.match(/Running \d+ agents?/)) {
      status.push(`▸ ${trimmed}`);
    }
    // Thought for Xs
    else if (trimmed.match(/thought for \d+/i)) {
      status.push(`  ${trimmed}`);
    }
    // Idle prompt detection
    else if (trimmed.match(/[❯>]\s*$/) || trimmed.match(/bypass permissions|hold Space/)) {
      isIdle = true;
    }
  }

  return status.length > 0
    ? status.slice(-40).join("\n")
    : isIdle
      ? "__idle__"
      : "";
}

async function captureTmuxPane(sessionName: string): Promise<string> {
  try {
    // Resize pane wider so long lines aren't wrapped/truncated in the buffer
    await $`tmux resize-window -t ${sessionName} -x 220`.nothrow().quiet();
    const result = await $`tmux capture-pane -t ${sessionName} -p -J -S -120`.text();
    return result;
  } catch {
    return "";
  }
}

let _discordClient: Client | null = null;

// Bump watch to bottom: delete + resend (used when new messages push it up)
async function bumpWatchToBottom(state: WatchState): Promise<void> {
  if (!_discordClient) return;
  try {
    const channel = await _discordClient.channels.fetch(state.channelId);
    if (!channel?.isTextBased()) return;
    const ch = channel as any;

    // Read current content before deleting
    let oldContent = "";
    let oldFiles: any[] = [];
    try {
      const oldMsg = await ch.messages.fetch(state.messageId);
      oldContent = oldMsg.content || "";
      if (oldMsg.attachments.size > 0) {
        // Re-upload the attachment
        const att = oldMsg.attachments.first();
        if (att) {
          const resp = await fetch(att.url);
          const buf = Buffer.from(await resp.arrayBuffer());
          oldFiles = [new AttachmentBuilder(buf, { name: att.name || "session.txt" })];
        }
      }
    } catch {}

    try { await ch.messages.delete(state.messageId); } catch {}
    const msg = await ch.send({
      content: oldContent || `**${state.sessionName}** — watching...`,
      files: oldFiles.length ? oldFiles : undefined,
    });
    state.messageId = msg.id;
  } catch {}
}

async function editWatchMessage(
  state: WatchState,
  content: string,
  paneText?: string
): Promise<void> {
  if (!_discordClient) return;
  try {
    const channel = await _discordClient.channels.fetch(state.channelId);
    if (!channel?.isTextBased()) return;
    const ch = channel as any;

    // Edit in place (no flicker, no notifications)
    if (paneText && paneText.length > 100) {
      const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
      const header = `**${state.sessionName}** — working (${elapsed}s)`;
      const attachment = new AttachmentBuilder(Buffer.from(paneText, "utf8"), {
        name: "session.txt",
      });
      await ch.messages.edit(state.messageId, {
        content: header,
        files: [attachment],
      });
    } else {
      await ch.messages.edit(state.messageId, { content });
    }
  } catch (e: any) {
    // Message was deleted — recreate it
    if (e.code === 10008) {
      try {
        const channel = await _discordClient!.channels.fetch(state.channelId);
        if (channel?.isTextBased()) {
          const sendOpts: any = { content: content || `**${state.sessionName}** — watching...` };
          if (paneText && paneText.length > 100) {
            sendOpts.files = [new AttachmentBuilder(Buffer.from(paneText, "utf8"), { name: "session.txt" })];
          }
          const msg = await (channel as any).send(sendOpts);
          state.messageId = msg.id;
        }
      } catch {}
    }
    console.error(`[watcher] Edit failed:`, e.message);
  }
}

// ── Log mode: raw diff-based extraction ──────────────────────────────────
// No regex parsing of Claude's output. We diff raw pane snapshots
// and post genuinely new lines. The only "parsing" is detecting the
// idle prompt to know when to stop.

function isIdleLine(line: string): boolean {
  const t = line.trim();
  return !!(t.match(/[❯>]\s*$/) || t.match(/bypass permissions|hold Space|shift\+tab/));
}

// Diff two pane snapshots and return only the lines that are new
function diffPaneLines(
  prevLines: string[],
  currLines: string[]
): string[] {
  // Build a multiset of previous lines (handle duplicates)
  const prevCounts = new Map<string, number>();
  for (const l of prevLines) {
    const t = l.trim();
    if (t) prevCounts.set(t, (prevCounts.get(t) || 0) + 1);
  }

  const newLines: string[] = [];
  for (const l of currLines) {
    const t = l.trim();
    if (!t) continue;
    const count = prevCounts.get(t) || 0;
    if (count > 0) {
      prevCounts.set(t, count - 1); // consume one occurrence
    } else {
      newLines.push(t);
    }
  }
  return newLines;
}

async function watchTickLog(state: WatchState): Promise<void> {
  if (!_discordClient) return;

  const raw = await captureTmuxPane(state.tmuxSession);
  if (!raw) {
    state.idleCount++;
    if (state.idleCount >= IDLE_STOP_COUNT) stopWatch(state.channelId, "session gone");
    return;
  }

  const currLines = raw.split("\n");
  const prevLines = state.lastContent ? state.lastContent.split("\n") : [];
  state.lastContent = raw;

  // Check idle
  const isIdle = currLines.some((l) => isIdleLine(l));

  // Diff to find new lines
  const newLines = diffPaneLines(prevLines, currLines);

  if (newLines.length === 0) {
    if (isIdle) {
      state.idleCount++;
      if (state.idleCount >= IDLE_STOP_COUNT) {
        const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
        const total = state.logBuffer.length;
        await editWatchMessage(
          state,
          `**${state.sessionName}** — done (${elapsed}s, ${total} entries)`
        );
        stopWatch(state.channelId, "idle");
      }
    }
    return;
  }

  state.idleCount = 0;

  const timestamp = new Date().toLocaleTimeString("en-US", {
    hour12: false,
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });

  for (const line of newLines) {
    let display = line.length > 150 ? line.slice(0, 147) + "..." : line;
    state.logBuffer.push(`\`${timestamp}\` ${display}`);
  }

  // Build message: header + as many recent entries as fit in 1900 chars
  const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
  const header = `**${state.sessionName}** — log (${elapsed}s, ${state.logBuffer.length} entries)\n`;

  // Take entries from the end, fitting within limit
  const maxBody = 1900 - header.length;
  const display: string[] = [];
  let bodyLen = 0;
  for (let i = state.logBuffer.length - 1; i >= 0; i--) {
    const line = state.logBuffer[i];
    if (bodyLen + line.length + 1 > maxBody) break;
    display.unshift(line);
    bodyLen += line.length + 1;
  }

  const skipped = state.logBuffer.length - display.length;
  const skipNote = skipped > 0 ? `_(${skipped} earlier entries)_\n` : "";

  await editWatchMessage(state, `${header}${skipNote}${display.join("\n")}`);
}

async function sendSilent(channelId: string, content: string): Promise<void> {
  if (!_discordClient) return;
  try {
    const channel = await _discordClient.channels.fetch(channelId);
    if (channel?.isTextBased()) {
      await (channel as any).send({
        content,
        flags: 1 << 12, // SUPPRESS_NOTIFICATIONS
      });
    }
  } catch {}
}

async function watchTick(state: WatchState): Promise<void> {
  if (state.mode === "log") return watchTickLog(state);

  // ── Live mode (snapshot as scrollable file) ──
  if (!_discordClient) return;

  const raw = await captureTmuxPane(state.tmuxSession);
  if (!raw) {
    state.idleCount++;
    if (state.idleCount >= IDLE_STOP_COUNT) stopWatch(state.channelId, "session gone");
    return;
  }

  // Check idle by looking at the raw pane
  const lines = raw.split("\n");
  const isIdle = lines.some((l) => isIdleLine(l));

  if (isIdle && raw.trim() === state.lastContent?.trim()) {
    state.idleCount++;
    if (state.idleCount >= IDLE_STOP_COUNT) {
      const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
      await editWatchMessage(
        state,
        `**${state.sessionName}** — done (${elapsed}s)`
      );
      stopWatch(state.channelId, "idle");
    }
    return;
  }

  // Skip if pane hasn't changed
  if (raw.trim() === state.lastContent?.trim()) return;

  state.lastContent = raw;
  state.idleCount = 0;

  // Build code block from the tail of the pane that fits in Discord's limit
  const elapsed = Math.round((Date.now() - state.startedAt) / 1000);
  const header = `**${state.sessionName}** — working (${elapsed}s)\n`;
  const maxBody = 2000 - header.length - 10; // 10 for ``` markers + newlines

  // Filter TUI chrome from ALL lines (separators, prompt, keybinding hints)
  // Keep status bar (model, tokens, cost, rate) — it's useful info
  const isTuiChrome = (line: string): boolean => {
    const t = line.trim();
    if (!t) return false; // blank lines kept for readability
    if (t.match(/^[─━═▔▁_\-─]{3,}$/)) return true;     // separator (pure)
    if (t.match(/^[─━═▔▁_\-─\s]+$/) && t.length > 3) return true; // separator with spaces
    if (t.match(/^[❯>]\s*$/)) return true;               // bare prompt
    if (t.match(/^❯\s*$/)) return true;                  // bare prompt (unicode)
    if (t.match(/bypass permissions/)) return true;
    if (t.match(/shift\+tab/)) return true;
    if (t.match(/^⏵⏵/)) return true;
    return false;
  };

  const allLines = raw.split("\n").filter((line) => !isTuiChrome(line));

  // Strip leading/trailing blank lines
  while (allLines.length && !allLines[0].trim()) allLines.shift();
  while (allLines.length && !allLines[allLines.length - 1].trim()) allLines.pop();

  const display: string[] = [];
  let bodyLen = 0;
  for (let i = allLines.length - 1; i >= 0; i--) {
    const line = allLines[i];
    if (bodyLen + line.length + 1 > maxBody) break;
    display.unshift(line);
    bodyLen += line.length + 1;
  }

  const content = `${header}\`\`\`\n${display.join("\n")}\n\`\`\``;
  await editWatchMessage(state, content);
}

function stopWatch(channelId: string, reason: string): void {
  const state = activeWatches.get(channelId);
  if (!state) return;
  clearInterval(state.interval);
  activeWatches.delete(channelId);
  console.log(`[watcher] Stopped watch for ${state.sessionName}: ${reason}`);
}

async function handleSessionSnapshot(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running.`;
  }

  // Capture a large chunk of the pane
  let paneText = "";
  try {
    await $`tmux resize-window -t ${session.tmux} -x 220`.nothrow().quiet();
    paneText = await $`tmux capture-pane -t ${session.tmux} -p -J -S -500`.text();
  } catch {
    return "Failed to capture session pane.";
  }

  // Strip TUI chrome from bottom
  const lines = paneText.split("\n");
  while (lines.length) {
    const last = lines[lines.length - 1].trim();
    if (
      !last ||
      last.match(/^[─━═▔▁_]{3,}$/) ||
      last.match(/^[❯>]\s*$/) ||
      last.match(/bypass permissions/) ||
      last.match(/auto-compact/) ||
      last.match(/shift\+tab/) ||
      last.match(/esc to interrupt/) ||
      last.match(/hold Space/)
    ) {
      lines.pop();
    } else {
      break;
    }
  }
  // Strip leading blank lines
  while (lines.length && !lines[0].trim()) lines.shift();

  const cleaned = lines.join("\n").trimEnd();
  if (!cleaned) return "Session pane is empty.";

  // Return a marker so the router uploads the file
  return JSON.stringify({ __snapshot: true, name: session.name, content: cleaned });
}

async function handleSessionHistory(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running.`;
  }

  // Capture the ENTIRE scrollback buffer
  let paneText = "";
  try {
    await $`tmux resize-window -t ${session.tmux} -x 220`.nothrow().quiet();
    // -S - = from the very start, -E - = to the very end
    paneText = await $`tmux capture-pane -t ${session.tmux} -p -J -S - -E -`.text();
  } catch {
    return "Failed to capture session history.";
  }

  // Strip TUI chrome from bottom
  const lines = paneText.split("\n");
  while (lines.length) {
    const last = lines[lines.length - 1].trim();
    if (
      !last ||
      last.match(/^[─━═▔▁_]{3,}$/) ||
      last.match(/^[❯>]\s*$/) ||
      last.match(/bypass permissions/) ||
      last.match(/auto-compact/) ||
      last.match(/shift\+tab/) ||
      last.match(/esc to interrupt/) ||
      last.match(/hold Space/)
    ) {
      lines.pop();
    } else {
      break;
    }
  }
  while (lines.length && !lines[0].trim()) lines.shift();

  const cleaned = lines.join("\n").trimEnd();
  if (!cleaned) return "Session history is empty.";

  return JSON.stringify({ __snapshot: true, name: `${session.name}-history`, content: cleaned });
}

// Map friendly names to tmux key sequences
const KEY_MAP: Record<string, string> = {
  yes: "Enter",
  no: "Escape",
  esc: "Escape",
  escape: "Escape",
  enter: "Enter",
  tab: "Tab",
  up: "Up",
  down: "Down",
  left: "Left",
  right: "Right",
  space: "Space",
  "shift+tab": "BTab",
  "ctrl+c": "C-c",
  "ctrl+d": "C-d",
};

async function handleSessionSend(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;
  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running.`;
  }

  const rawInput = interaction.options.getString("input", true);
  const lower = rawInput.toLowerCase().trim();

  // Check if it's a special key
  const mappedKey = KEY_MAP[lower];

  try {
    if (mappedKey) {
      // Send as a tmux key
      await $`tmux send-keys -t ${session.tmux} ${mappedKey}`.quiet();
      return `Sent key \`${lower}\` → \`${mappedKey}\` to session \`${session.name}\``;
    } else if (lower === "1") {
      // Option 1 — cursor starts here, just press Enter
      await $`tmux send-keys -t ${session.tmux} Enter`.quiet();
      return `Selected option 1 (Enter) in session \`${session.name}\``;
    } else if (lower === "2") {
      // Option 2 — Down then Enter
      await $`tmux send-keys -t ${session.tmux} Down Enter`.quiet();
      return `Selected option 2 (Down+Enter) in session \`${session.name}\``;
    } else if (lower === "3") {
      // Option 3 — Down Down Enter
      await $`tmux send-keys -t ${session.tmux} Down Down Enter`.quiet();
      return `Selected option 3 (Down+Down+Enter) in session \`${session.name}\``;
    } else if (lower === "4") {
      await $`tmux send-keys -t ${session.tmux} Down Down Down Enter`.quiet();
      return `Selected option 4 in session \`${session.name}\``;
    } else if (lower === "5") {
      await $`tmux send-keys -t ${session.tmux} Down Down Down Down Enter`.quiet();
      return `Selected option 5 in session \`${session.name}\``;
    } else {
      // Send as text + Enter
      const escaped = escapeForTmux(rawInput);
      await $`tmux send-keys -t ${session.tmux} ${escaped} Enter`.quiet();
      return `Sent text to session \`${session.name}\`:\n> ${rawInput.length > 200 ? rawInput.slice(0, 200) + "..." : rawInput}`;
    }
  } catch (e: any) {
    return `Failed to send: ${e.message}`;
  }
}

async function handleSessionWatch(
  interaction: ChatInputCommandInteraction
): Promise<string> {
  const channelId = interaction.channelId;

  // Toggle off if already watching
  if (activeWatches.has(channelId)) {
    stopWatch(channelId, "user toggled off");
    return "Activity streaming stopped.";
  }

  const session = findSessionByChannel(channelId);
  if (!session) {
    return "No session registered for this channel. Try `/discover` first.";
  }

  const alive = await isTmuxAlive(session.tmux);
  if (!alive) {
    return `Session \`${session.tmux}\` is not running.`;
  }

  const mode = (interaction.options.getString("mode") ?? "live") as WatchMode;

  return JSON.stringify({
    __watch: true,
    tmux: session.tmux,
    name: session.name,
    mode,
  });
}

async function startAutoWatch(channelId: string, mode: WatchMode = "live"): Promise<void> {
  if (activeWatches.has(channelId) || !_discordClient) return;

  const session = findSessionByChannel(channelId);
  if (!session) return;

  // Don't auto-start watch on a parent channel if any of its threads have active watches
  // (thread messages leak to parent's plugin session — would show duplicate activity)
  if (session.type === "channel") {
    const registry = readSessionsRegistry();
    for (const [id, info] of Object.entries(registry)) {
      if ((info as any).parent === channelId && activeWatches.has(id)) {
        console.log(`[watcher] Skipping auto-watch for parent ${channelId} — thread ${id} is being watched`);
        return;
      }
    }
  }

  try {
    const channel = await _discordClient.channels.fetch(channelId);
    if (!channel?.isTextBased()) return;

    const modeLabel = mode === "log" ? "log mode" : "live mode";
    const msg = await (channel as any).send({
      content: `**${session.name}** — watching (${modeLabel})...\nWaiting for agent output...`,
      flags: 1 << 12, // SUPPRESS_NOTIFICATIONS
    });

    const state: WatchState = {
      channelId,
      messageId: msg.id,
      tmuxSession: session.tmux,
      sessionName: session.name,
      interval: setInterval(() => watchTick(state), WATCH_INTERVAL_MS),
      lastContent: "",
      lastRawLines: new Set(),
      logBuffer: [],
      logMessageId: "",
      mode,
      idleCount: 0,
      startedAt: Date.now(),
    };
    activeWatches.set(channelId, state);
    console.log(`[watcher] Auto-started watch (${modeLabel}) for ${session.name}`);
  } catch (e: any) {
    console.error(`[watcher] Auto-start failed:`, e.message);
  }
}

// ── Autocomplete Handler ──────────────────────────────────────────────────

async function handleAutocomplete(
  interaction: AutocompleteInteraction
): Promise<void> {
  const focused = interaction.options.getFocused(true);

  if (
    interaction.commandName === "session" &&
    focused.name === "path"
  ) {
    const workdirMap = readWorkdirMap();
    const typed = (focused.value as string).toLowerCase();

    const choices = Object.entries(workdirMap)
      .filter(
        ([name, path]) =>
          name.toLowerCase().includes(typed) ||
          path.toLowerCase().includes(typed)
      )
      .slice(0, 25)
      .map(([name, path]) => {
        const displayPath = path.replace(/\$HOME/g, "~");
        return {
          name: `${name} → ${displayPath}`.slice(0, 100),
          value: path.replace(/\$HOME/g, homedir()),
        };
      });

    await interaction.respond(choices);
  } else if (
    interaction.commandName === "run" &&
    focused.name === "skill"
  ) {
    const typed = (focused.value as string).toLowerCase().trim();
    const globalSkills = getSkillsWithCache();

    // Get project-local skills for this channel's workdir
    const channelId = interaction.channelId;
    const wdFile = join(SESSIONS_DIR, channelId, ".workdir");
    let projectSkills: Array<{ name: string; description: string }> = [];
    let workdirLabel = "";
    try {
      if (existsSync(wdFile)) {
        const wd = readFileSync(wdFile, "utf8").trim();
        projectSkills = scanProjectSkills(wd);
        workdirLabel = wd.replace(homedir(), "~").split("/").pop() || "";
      }
    } catch {}

    if (!typed) {
      // Empty input: show project skills first, then category summaries
      const choices: Array<{ name: string; value: string }> = [];

      // Project-local skills first
      if (projectSkills.length > 0) {
        for (const s of projectSkills.slice(0, 5)) {
          choices.push({
            name: `⭐ /${s.name} — [${workdirLabel}] ${s.description}`.slice(0, 100),
            value: s.name,
          });
        }
      }

      // Category summaries for plugin skills
      const categories: Record<string, number> = {};
      const userSkillCount = globalSkills.filter(
        (s) => !s.name.includes(":")
      ).length;

      for (const s of globalSkills) {
        const colonIdx = s.name.indexOf(":");
        if (colonIdx > 0) {
          const prefix = s.name.slice(0, colonIdx);
          categories[prefix] = (categories[prefix] || 0) + 1;
        }
      }

      // User skills category
      choices.push({
        name: `📂 user skills (${userSkillCount}) — type any name to search`.slice(0, 100),
        value: "a", // starts filtering from 'a' to show user skills
      });

      // Plugin categories sorted by count
      const sorted = Object.entries(categories).sort((a, b) => b[1] - a[1]);
      for (const [prefix, count] of sorted) {
        if (choices.length >= 25) break;
        choices.push({
          name: `📦 ${prefix}:* (${count} skills)`.slice(0, 100),
          value: prefix,
        });
      }

      await interaction.respond(choices.slice(0, 25));
    } else {
      // Filtered: project skills first, then global matches
      const projectNames = new Set(projectSkills.map((s) => s.name));
      const projectMatches = projectSkills
        .filter((s) => s.name.toLowerCase().includes(typed))
        .map((s) => ({
          name: `⭐ /${s.name} — [${workdirLabel}] ${s.description}`.slice(0, 100),
          value: s.name,
        }));

      const globalMatches = globalSkills
        .filter(
          (s) =>
            s.name.toLowerCase().includes(typed) &&
            !projectNames.has(s.name)
        )
        .map((s) => ({
          name: `/${s.name} — ${s.description}`.slice(0, 100),
          value: s.name,
        }));

      const choices = [...projectMatches, ...globalMatches].slice(0, 25);
      await interaction.respond(choices);
    }
  } else if (
    interaction.commandName === "session" &&
    focused.name === "input"
  ) {
    const typed = (focused.value as string).toLowerCase().trim();
    const commonChoices = [
      { name: "1 — Select option 1 (Enter — cursor starts here)", value: "1" },
      { name: "2 — Select option 2 (Down + Enter)", value: "2" },
      { name: "3 — Select option 3 (Down×2 + Enter)", value: "3" },
      { name: "yes — Press Enter (confirm current selection)", value: "yes" },
      { name: "no — Press Escape (cancel)", value: "no" },
      { name: "enter — Press Enter", value: "enter" },
      { name: "esc — Cancel / dismiss", value: "esc" },
      { name: "tab — Next option", value: "tab" },
      { name: "shift+tab — Toggle permissions mode", value: "shift+tab" },
      { name: "up — Navigate up", value: "up" },
      { name: "down — Navigate down", value: "down" },
      { name: "space — Select / toggle", value: "space" },
      { name: "ctrl+c — Interrupt", value: "ctrl+c" },
    ];

    const filtered = typed
      ? commonChoices.filter((c) => c.name.toLowerCase().includes(typed) || c.value.includes(typed))
      : commonChoices;

    await interaction.respond(filtered.slice(0, 25));
  } else if (
    interaction.commandName === "session" &&
    focused.name === "name" &&
    interaction.options.getSubcommand() === "profile"
  ) {
    const typed = (focused.value as string).toLowerCase().trim();
    const profiles = listAvailableProfiles();
    const current = readProfile(interaction.channelId);

    const choices = profiles
      .filter((p) => !typed || p.toLowerCase().includes(typed))
      .map((p) => ({
        name: `${p}${p === current ? " (current)" : ""}`,
        value: p,
      }));

    await interaction.respond(choices.slice(0, 25));
  }
}

// ── Interaction Router ────────────────────────────────────────────────────

async function handleInteraction(
  interaction: ChatInputCommandInteraction
): Promise<void> {
  const { commandName } = interaction;

  // Determine if response should be ephemeral
  const isEphemeral =
    (commandName === "session" &&
      interaction.options.getSubcommand() === "status") ||
    (commandName === "skills" &&
      interaction.options.getSubcommand() === "list");

  // Defer reply
  await interaction.deferReply({ ephemeral: isEphemeral });

  let response: string;

  try {
    switch (commandName) {
      case "session": {
        const sub = interaction.options.getSubcommand();
        switch (sub) {
          case "status":
            response = await handleSessionStatus(interaction);
            break;
          case "restart":
            response = await handleSessionRestart(interaction);
            break;
          case "refresh":
            response = await handleSessionRefresh(interaction);
            break;
          case "kill":
            response = await handleSessionKill(interaction);
            break;
          case "wake":
            response = await handleSessionWake(interaction);
            break;
          case "workdir":
            response = await handleSessionWorkdir(interaction);
            break;
          case "watch":
            response = await handleSessionWatch(interaction);
            break;
          case "snapshot":
            response = await handleSessionSnapshot(interaction);
            break;
          case "history":
            response = await handleSessionHistory(interaction);
            break;
          case "send":
            response = await handleSessionSend(interaction);
            break;
          case "profile":
            response = await handleSessionProfile(interaction);
            break;
          default:
            response = `Unknown subcommand: ${sub}`;
        }
        break;
      }
      case "skills": {
        const sub = interaction.options.getSubcommand();
        switch (sub) {
          case "list":
            response = await handleSkillsList(interaction);
            break;
          case "install":
            response = await handleSkillsInstall(interaction);
            break;
          default:
            response = `Unknown subcommand: ${sub}`;
        }
        break;
      }
      case "discover":
        response = await handleDiscover(interaction);
        break;
      case "ask":
        response = await handleAsk(interaction);
        break;
      case "run":
        response = await handleRun(interaction);
        break;
      default:
        response = `Unknown command: ${commandName}`;
    }
  } catch (e: any) {
    response = `Error: ${e.message}`;
    console.error(`[slash-daemon] Error handling /${commandName}:`, e);
  }

  // Edit the deferred response
  try {
    // Check for watch start signal
    if (response.startsWith("{") && response.includes('"__watch"')) {
      const parsed = JSON.parse(response);
      const mode: WatchMode = parsed.mode || "live";
      const modeLabel = mode === "log" ? "log mode" : "live mode";
      const msg = await interaction.editReply({
        content: `**${parsed.name}** — watching (${modeLabel})...\n\`\`\`\nWaiting for agent output...\n\`\`\``,
      });

      const messageId = typeof msg === "string" ? msg : msg.id;
      const channelId = interaction.channelId;

      const state: WatchState = {
        channelId,
        messageId,
        tmuxSession: parsed.tmux,
        sessionName: parsed.name,
        interval: setInterval(() => watchTick(state), WATCH_INTERVAL_MS),
        lastContent: "",
        lastRawLines: new Set(),
        logBuffer: [],
        logMessageId: "",
        mode,
        idleCount: 0,
        startedAt: Date.now(),
      };
      activeWatches.set(channelId, state);
      console.log(`[watcher] Started watch (${modeLabel}) for ${parsed.name} in ${channelId}`);
    }
    // Check for snapshot signal — upload full pane as .txt file
    else if (response.startsWith("{") && response.includes('"__snapshot"')) {
      const parsed = JSON.parse(response);
      const attachment = new AttachmentBuilder(
        Buffer.from(parsed.content, "utf8"),
        { name: `${parsed.name}-snapshot.txt` }
      );
      await interaction.editReply({
        content: `**${parsed.name}** — full session snapshot`,
        files: [attachment],
      });
    }
    // Check if response contains an embed
    else if (response.startsWith("{") && response.includes('"embed"')) {
      const parsed = JSON.parse(response);
      await interaction.editReply({ embeds: [parsed.embed] });
    } else {
      // Truncate if too long for Discord
      if (response.length > 2000) {
        response = response.slice(0, 1997) + "...";
      }
      await interaction.editReply({ content: response });
    }
  } catch (e: any) {
    console.error("[slash-daemon] Failed to edit reply:", e);
  }
}

// ── Register Commands ─────────────────────────────────────────────────────

async function registerCommands(rest: REST): Promise<void> {
  console.log("[slash-daemon] Fetching application ID...");

  const app = (await rest.get(Routes.oauth2CurrentApplication())) as {
    id: string;
    name: string;
  };
  const appId = app.id;
  console.log(`[slash-daemon] Application: ${app.name} (${appId})`);

  console.log(
    `[slash-daemon] Registering ${SLASH_COMMANDS.length} slash commands for guild ${GUILD_ID}...`
  );

  await rest.put(Routes.applicationGuildCommands(appId, GUILD_ID), {
    body: SLASH_COMMANDS,
  });

  console.log("[slash-daemon] Slash commands registered successfully.");
}

// ── Main ──────────────────────────────────────────────────────────────────

async function main() {
  console.log("[slash-daemon] Starting Discord slash command daemon...");
  console.log(`[slash-daemon] Sessions dir: ${SESSIONS_DIR}`);
  console.log(`[slash-daemon] Manager: ${MANAGER_PATH}`);

  // Set up REST client and register commands
  const rest = new REST({ version: "10" }).setToken(BOT_TOKEN);
  await registerCommands(rest);

  // Create the Gateway client
  const client = new Client({
    intents: [
      GatewayIntentBits.Guilds,
      GatewayIntentBits.GuildMessages,
      GatewayIntentBits.MessageContent,
    ],
  });

  client.on("ready", () => {
    _discordClient = client;
    console.log(
      `[slash-daemon] Connected as ${client.user?.tag} — listening for slash commands`
    );
  });

  client.on("interactionCreate", async (interaction) => {
    if (interaction.isAutocomplete()) {
      try {
        await handleAutocomplete(interaction as AutocompleteInteraction);
      } catch (e) {
        console.error("[slash-daemon] Autocomplete error:", e);
      }
      return;
    }

    if (interaction.isChatInputCommand()) {
      await handleInteraction(interaction as ChatInputCommandInteraction);
    }
  });

  // Auto-start watch + bump to bottom when user sends a message
  client.on("messageCreate", async (message) => {
    if (message.author.bot) return;

    // Use the exact channel/thread ID the message was posted in
    const channelId = message.channelId;
    const isThread = message.channel.isThread();
    const parentId = isThread ? (message.channel as any).parentId : null;

    // If already watching this exact channel/thread, just bump to bottom
    const watch = activeWatches.get(channelId);
    if (watch) {
      setTimeout(() => bumpWatchToBottom(watch), 1500);
      return;
    }

    // Auto-start watch for the channel/thread where the message was posted
    const session = findSessionByChannel(channelId);
    if (session) {
      const alive = await isTmuxAlive(session.tmux);
      if (alive) {
        setTimeout(() => startAutoWatch(channelId), 3000);
      }
    }

    // If this is a thread message, do NOT also trigger the parent channel's watch.
    // The parent's Discord plugin session may pick up the message, but we don't
    // want the parent's watch to show thread activity.
    if (isThread && parentId) {
      const parentWatch = activeWatches.get(parentId);
      if (parentWatch) {
        // Parent watch is active but this message is in a thread — ignore
        // (don't bump parent to bottom for thread messages)
        return;
      }
    }
  });

  // Graceful shutdown
  const shutdown = () => {
    console.log("[slash-daemon] Shutting down...");
    for (const [channelId] of activeWatches) {
      stopWatch(channelId, "daemon shutdown");
    }
    client.destroy();
    process.exit(0);
  };
  process.on("SIGINT", shutdown);
  process.on("SIGTERM", shutdown);

  await client.login(BOT_TOKEN);
}

main().catch((e) => {
  console.error("[slash-daemon] Fatal error:", e);
  process.exit(1);
});
