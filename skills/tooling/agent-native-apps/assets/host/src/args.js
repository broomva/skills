// Host command line, parsed without Electron so the policy is testable.

import path from "node:path";
import { parseMaxTier } from "./capabilities.js";

const STRING_FLAGS = new Set(["home", "apps-dir", "max-tier"]);
const BOOLEAN_FLAGS = new Set(["selftest"]);
export const COMMANDS = new Set(["serve", "install", "uninstall", "grant", "list"]);

export class ArgsError extends Error {}

/**
 * Parse argv (after Electron's own). `--name=value` for string flags, `--name`
 * for boolean ones. Single-dash tokens are macOS/Chromium launch noise
 * (-psn_…, -AppleLanguages) and are skipped with the value that follows a
 * bare `-Name`. Pure.
 */
export function parseArgs(argv) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i];
    if (arg.startsWith("--")) {
      const m = /^--([a-z-]+)(?:=(.*))?$/s.exec(arg);
      if (!m) throw new ArgsError(`Malformed flag "${arg}".`);
      const [, name, value] = m;
      if (STRING_FLAGS.has(name)) {
        if (value === undefined || value === "")
          throw new ArgsError(`--${name} needs a value: --${name}=<value>.`);
        flags[name] = value;
      } else if (BOOLEAN_FLAGS.has(name)) {
        if (value !== undefined) throw new ArgsError(`--${name} takes no value.`);
        flags[name] = true;
      } else {
        throw new ArgsError(`Unknown flag --${name}.`);
      }
    } else if (arg.startsWith("-")) {
      if (/^-[A-Z]/.test(arg) && i + 1 < argv.length && !argv[i + 1].startsWith("-")) i++;
    } else {
      positional.push(arg);
    }
  }
  return { flags, positional };
}

/** Validated host configuration. Pure. */
export function hostConfig(flags, { defaultHome, defaultAppsDir }) {
  return {
    home: path.resolve(flags.home ?? defaultHome),
    appsDir: path.resolve(flags["apps-dir"] ?? defaultAppsDir),
    maxTier: parseMaxTier(flags["max-tier"] ?? 3),
    selftest: flags.selftest === true,
  };
}

/** The command, with path arguments made absolute against the caller's cwd. Pure. */
export function resolveCommand(positional, cwd) {
  const [cmd = "serve", ...rest] = positional;
  if (!COMMANDS.has(cmd)) throw new ArgsError(`Unknown command "${cmd}".`);
  if (cmd === "install") return [cmd, path.resolve(cwd, rest[0] ?? ".")];
  if ((cmd === "uninstall" || cmd === "grant") && !rest[0]) throw new ArgsError(`${cmd} needs an app id.`);
  return [cmd, ...rest];
}
