/**
 * Every `file.ts:123` in a spec is a claim about code that moves underneath it.
 *
 * A spec written before the change it describes becomes a false description of
 * the tree with nothing marking it stale -- the citation still LOOKS precise
 * long after the line it names has shifted. Writing the UI-layer spec produced
 * two of these in one sitting (`handlers.ts:874` when the fork is at 880,
 * `hub.test.ts:205` when the assertion is at 206), and both read as
 * authoritative. Precision is not accuracy, and only one of them is checkable.
 *
 * So: resolve every cited line and require the file to still have one.
 *
 * The rule that keeps this from being noise -- ONLY `path:line` forms are
 * checked. A bare path with no line is a PROPOSAL (`src/view/frame.ts`, a file
 * the spec argues should exist), and demanding those resolve would make it
 * impossible to spec anything not yet written. A line number is the thing that
 * asserts present-tense content, so a line number is the thing that is gated.
 *
 * ---------------------------------------------------------------------------
 * WHAT THE MOVE INTO THE MONOREPO CHANGED, AND WHY IT IS NOT A REPATH
 *
 * This checker used to live beside the code it indexed, in a repository that
 * contained one project. Both of its escape hatches were safe there and became
 * unsafe here, in opposite directions:
 *
 *   1. A MISSING SPEC DIRECTORY RETURNED ZERO FAILURES. The old code read
 *      `docs/specs` relative to the repo root and did `if (!existsSync) return []`.
 *      The specs are now in a different directory from the code, so the single
 *      most likely future breakage -- someone moves one of the two -- was the
 *      exact case that reported success. A gate whose failure mode is silence
 *      is not a gate. It now throws.
 *
 *   2. AN AMBIGUOUS BASENAME WAS SILENTLY SKIPPED. `handlers.ts:874` was
 *      resolved by indexing every file in the tree by basename and skipping the
 *      citation if more than one matched. In a single-project repo that was a
 *      rare, honest limitation. In a 90-skill monorepo, indexing from the repo
 *      root makes collisions the COMMON case -- `index.ts`, `types.ts`,
 *      `handlers.ts` recur across skills -- so nearly every citation would be
 *      skipped and the gate would pass while checking almost nothing.
 *
 *      The fix is not to report collisions; it is to stop creating them. The
 *      code root is scoped to the one tree these specs actually cite. A
 *      collision inside that tree is now genuinely rare, so it is reported as a
 *      failure rather than skipped -- an unresolvable citation is not something
 *      the reader can act on either way.
 *
 * The third hazard is a spec with no citations at all, which passes every
 * assertion above without exercising one. That is asserted against explicitly,
 * the same way the sibling pytest suite asserts its own fixture is not empty.
 */

import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { extname, join, relative, resolve } from "node:path";

/** Where the specs are, relative to this package. */
const SPEC_DIR = "docs";
/**
 * Bare-basename citations are resolved ONLY inside this tree. Scoped
 * deliberately -- see header note 2.
 */
const CODE_ROOT = "../skills/simulation/parallax/runtime";
/**
 * Path-bearing citations are resolved from here instead.
 *
 * The specs write monorepo-root-relative paths
 * (`skills/simulation/parallax/runtime/src/core/ops.ts:200`) rather than paths
 * relative to the runtime, and that is the right call for a reader: in a repo
 * with 90 skills, `src/core/ops.ts` is ambiguous prose and the full path is
 * not. Resolving those against CODE_ROOT would look for the runtime inside
 * itself, so an explicit path gets the repo root and a bare basename gets the
 * scoped tree. Both resolve; neither can collide.
 */
const REPO_ROOT = "..";
// The range separator accepts an en-dash and an em-dash as well as an ASCII
// hyphen. These specs are typeset prose and an editor that "fixes" 205-240
// into 205–240 would otherwise make the citation silently unmatched --
// invisible, and in the direction that reports success.
const CITE = /([A-Za-z0-9_\-./]+\.(?:ts|tsx|css|md)):(\d+)(?:[-–—](\d+))?/g;
const SKIP_DIRS = new Set(["node_modules", ".git", ".next", "out", "dist"]);

/** Index basename -> paths, so `handlers.ts:802` resolves without a full path. */
function indexTree(dir: string, acc: Map<string, string[]>): Map<string, string[]> {
  for (const name of readdirSync(dir)) {
    if (SKIP_DIRS.has(name) || name.startsWith(".")) continue;
    const full = join(dir, name);
    let s: ReturnType<typeof statSync>;
    try {
      s = statSync(full);
    } catch {
      continue;
    }
    if (s.isDirectory()) indexTree(full, acc);
    else if ([".ts", ".tsx", ".css", ".md"].includes(extname(name))) {
      acc.set(name, [...(acc.get(name) ?? []), full]);
    }
  }
  return acc;
}

export interface Failure {
  readonly spec: string;
  readonly cite: string;
  readonly reason: string;
}

export interface Report {
  readonly failures: Failure[];
  /** Citations actually resolved. Zero means this check proved nothing. */
  readonly checked: number;
  readonly specs: number;
}

export function checkSpecCitations(base = ".", codeRoot = CODE_ROOT): Report {
  const specDir = join(base, SPEC_DIR);
  if (!existsSync(specDir)) {
    // Deliberately fatal. See header note 1: this used to return [].
    throw new Error(
      `spec directory not found: ${resolve(specDir)}. ` +
        `If the specs moved, repoint SPEC_DIR -- do not delete this check.`,
    );
  }
  const code = join(base, codeRoot);
  if (!existsSync(code)) {
    throw new Error(
      `code root not found: ${resolve(code)}. ` +
        `If the runtime moved, repoint CODE_ROOT -- do not delete this check.`,
    );
  }

  const byName = indexTree(code, new Map());
  const failures: Failure[] = [];
  let checked = 0;

  const specs = readdirSync(specDir).filter((f) => f.endsWith(".html"));
  for (const spec of specs) {
    const text = readFileSync(join(specDir, spec), "utf8");
    for (const m of text.matchAll(CITE)) {
      const cite = m[0];
      const path = m[1];
      const lo = m[2];
      const hi = m[3];
      if (path === undefined || lo === undefined) continue;

      const candidates = path.includes("/")
        ? existsSync(join(base, REPO_ROOT, path))
          ? [join(base, REPO_ROOT, path)]
          : []
        : (byName.get(path) ?? []);

      if (candidates.length === 0) {
        failures.push({ spec, cite, reason: "cites a line in a file that does not exist" });
        continue;
      }
      if (candidates.length > 1) {
        // See header note 2. Reported, not skipped: the reader cannot act on an
        // unresolvable citation whichever way this branch goes.
        failures.push({
          spec,
          cite,
          reason:
            `ambiguous: ${candidates.length} files named ${path} under ${codeRoot} ` +
            `(${candidates.map((c) => relative(code, c)).join(", ")}). Cite a path, not a basename.`,
        });
        continue;
      }

      const target = candidates[0] as string;
      const lines = readFileSync(target, "utf8").split("\n").length;
      const last = Number(hi ?? lo);
      checked++;
      if (last > lines) {
        failures.push({
          spec,
          cite,
          reason: `cites line ${last} but ${relative(code, target)} has ${lines}`,
        });
      }
    }
  }
  return { failures, checked, specs: specs.length };
}

if (import.meta.main) {
  const { failures, checked, specs } = checkSpecCitations();
  for (const f of failures) console.error(`${f.spec}: ${f.cite} -- ${f.reason}`);

  // A run that resolved nothing is not a pass. Without this, deleting every
  // citation from every spec is the easiest way to make this check green.
  if (checked === 0 && failures.length === 0) {
    console.error(
      `spec citations: ${specs} spec(s) read and NOT ONE citation resolved. ` +
        `This check proved nothing -- either the specs stopped citing code, or the ` +
        `citation pattern no longer matches how they write them.`,
    );
    process.exit(1);
  }

  console.log(
    failures.length === 0
      ? `spec citations: ${checked} cited line(s) across ${specs} spec(s) all resolve`
      : `spec citations: ${failures.length} broken of ${checked + failures.length} across ${specs} spec(s)`,
  );
  process.exit(failures.length === 0 ? 0 : 1);
}
