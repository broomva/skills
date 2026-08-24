import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { COMMANDS, parseArgs } from "../src/cli";

/**
 * Every `parallax ...` command printed in the docs must actually run.
 *
 * This file exists because one did not. README.md advertised
 * `parallax accept --by <who> --acknowledge-unmapped`, which exits 2 with
 * MISSING_FLAG: accept needs --proposal. It was written, reviewed and merged past
 * a green suite, because nothing in the suite reads the documentation.
 *
 * A command a reader copies and cannot run is worse than an absent example: it
 * teaches them the tool is broken. So the docs are an input to the tests now.
 */

const DOCS = ["../README.md", "../AGENTS.md"].map((rel) => ({
  name: rel.replace("../", ""),
  text: readFileSync(fileURLToPath(new URL(rel, import.meta.url)), "utf8"),
}));

/** Every line that invokes the CLI, with trailing `# comments` stripped. */
function commandLines(markdown: string): string[] {
  const out: string[] = [];
  for (const raw of markdown.split("\n")) {
    const line = raw
      .trim()
      .replace(/\s+#.*$/, "")
      .trim();
    if (!line.startsWith("parallax ")) continue;
    // Skip shell plumbing. `<ref>` and `<who>` are PLACEHOLDERS, not redirection,
    // so angle brackets stay -- excluding them silently dropped three of the four
    // documented commands and left this suite asserting almost nothing.
    if (/[|$`]/.test(line)) continue;
    out.push(line);
  }
  return out;
}

/** `<id>` and `<who>` are placeholders for VALUES, which is all the parser needs. */
function tokens(line: string): string[] {
  return line.split(/\s+/).slice(1);
}

describe("the documentation runs", () => {
  test("the docs actually contain commands to check", () => {
    // Without this the suite below is vacuous: zero lines pass every assertion.
    // It has already earned its place -- an over-eager filter cut the four real
    // commands down to one and every per-command test still reported green.
    const total = DOCS.reduce((n, d) => n + commandLines(d.text).length, 0);
    expect(total).toBeGreaterThanOrEqual(4);
  });

  for (const doc of DOCS) {
    for (const line of commandLines(doc.text)) {
      test(`${doc.name}: \`${line}\``, () => {
        const parsed = parseArgs(tokens(line));
        expect(parsed.ok, `does not parse: ${JSON.stringify(parsed)}`).toBe(true);
        if (!parsed.ok) return;

        const spec = COMMANDS[parsed.value.command];
        expect(spec, `no such command "${parsed.value.command}"`).toBeDefined();
        if (spec === undefined) return;

        for (const flag of spec.required) {
          const given =
            (parsed.value.values[flag]?.length ?? 0) > 0 || parsed.value.flags[flag] === true;
          expect(given, `\`${line}\` omits required --${flag}`).toBe(true);
        }
        for (const flag of Object.keys(parsed.value.values)) {
          expect(spec.allowed, `--${flag} is not allowed on "${parsed.value.command}"`).toContain(
            flag,
          );
        }
      });
    }
  }
});
