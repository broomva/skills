#!/usr/bin/env bun
/**
 * keel probe-loader — discover and load probes from disk.
 *
 * ┌──────────────────────────────────────────────────────────────────────────┐
 * │ LOADING A PROBE EXECUTES ITS FILE.                                        │
 * │                                                                           │
 * │ A probe is a TypeScript module. `import` runs its top level. So this      │
 * │ module is only ever imported by the SANDBOX CHILD                         │
 * │ (`scripts/probe-sandbox.ts`) — never by `classify.ts`, which is the       │
 * │ parent holding the kill-timer. A synchronous `while(true)` at module      │
 * │ scope cannot be preempted in JS; the only real timeout is a process       │
 * │ handle held by somebody else.                                             │
 * └──────────────────────────────────────────────────────────────────────────┘
 *
 * This file LOCATES and LOADS. It does not judge, and it never calls `match`
 * or `assess` — calling them is the child's job, one try/catch per call.
 *
 * Contract (orchestrator-owned, see docs/plans/00-orchestration.md
 * "The sandbox contract"):
 *
 *     loadProbes(dirs: string[]): Promise<{ probes: Probe[]; warnings: string[] }>
 *
 * Rules it upholds:
 *  - A missing (or unreadable) probe dir is "no probes", never an error — and
 *    never a warning either, deliberately. This function cannot tell a dir the
 *    operator NAMED (a typo worth shouting about) from a default that most
 *    installs have never created (`~/.config/keel/probes`), because the contract
 *    hands it a flat `string[]`. Warning about both would make the useful case
 *    indistinguishable from boilerplate on every fresh install. The distinction
 *    is drawn one layer up, where explicitness is still known:
 *    `probe-sandbox.ts`'s `missingNamedDirWarnings()` warns for dirs that came
 *    from `--probe-dir`/`KEEL_PROBE_DIR`, and those warnings travel to the
 *    operator in `ClassifyOutput.warnings`.
 *  - A malformed probe is SKIPPED WITH A WARNING, never silently dropped.
 *    Silent drops are how a probe library rots: the run stays green and the
 *    library quietly shrinks.
 *  - Probe files are named `<id>.v<version>.ts`. When one id appears more than
 *    once, the HIGHEST version wins and every shadowed version is named in a
 *    warning. Ties break toward the later directory (a user-minted probe
 *    overrides a shipped one of the same version).
 *  - `loadProbes` never throws. Every failure becomes a warning, because a
 *    broken probe must not be able to take down a run — probes are a cache
 *    layer, and the pure-agentic path is the product.
 */

import { readdirSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { pathToFileURL } from 'node:url';
import type { Probe } from '../schemas/keel.ts';

/** `<id>.v<version>.ts` — the minted-probe filename shape. */
const VERSIONED_NAME = /^(.+)\.v(\d+)\.(ts|mts|js|mjs)$/;
const LOADABLE_EXT = /\.(ts|mts|js|mjs)$/;

interface Candidate {
  probe: Probe;
  file: string;
  /** index into the caller's `dirs`, so ties can break toward the later dir */
  dirIndex: number;
}

function errText(e: unknown): string {
  if (e instanceof Error) return `${e.name}: ${e.message}`;
  return String(e);
}

/**
 * Files we will try to import. Everything else in the directory (READMEs,
 * type declarations, `_helpers.ts`, dotfiles) is not a probe and is skipped
 * without comment — skipping a non-probe is not a dropped probe.
 */
function isProbeFile(name: string): boolean {
  if (name.startsWith('.') || name.startsWith('_')) return false;
  if (name.endsWith('.d.ts')) return false;
  if (name.endsWith('.test.ts') || name.endsWith('.spec.ts')) return false;
  return LOADABLE_EXT.test(name);
}

/**
 * Structural validation against the `Probe` interface.
 *
 * Deliberately shallow: shape only. We never call `match` or `assess` here —
 * that is probe code, and probe code runs exactly once per run, inside the
 * child's per-call try/catch. Returns the list of problems; empty means valid.
 */
function problemsWith(v: unknown): string[] {
  if (typeof v !== 'object' || v === null) {
    return [`export is ${v === null ? 'null' : typeof v}, expected an object`];
  }
  const o = v as Record<string, unknown>;
  const problems: string[] = [];
  const str = (k: string) => {
    const x = o[k];
    if (typeof x !== 'string' || x.trim() === '') problems.push(`missing or empty \`${k}\``);
  };
  str('id');
  str('mintedAt');
  str('mintedFrom');
  str('description');
  if (typeof o.version !== 'number' || !Number.isFinite(o.version)) {
    problems.push('missing or non-numeric `version`');
  }
  if (typeof o.match !== 'function') problems.push('missing `match(node)`');
  if (typeof o.assess !== 'function') problems.push('missing `assess(node)`');
  return problems;
}

export async function loadProbes(
  dirs: string[],
): Promise<{ probes: Probe[]; warnings: string[] }> {
  const warnings: string[] = [];
  const candidates: Candidate[] = [];
  const seenFiles = new Set<string>();

  for (let dirIndex = 0; dirIndex < dirs.length; dirIndex++) {
    let dir: string;
    try {
      dir = resolve(dirs[dirIndex]);
    } catch (e) {
      warnings.push(`probe dir skipped: ${String(dirs[dirIndex])} — ${errText(e)}`);
      continue;
    }

    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch {
      // A missing or unreadable probe dir is "no probes", never an error.
      // The zero-probe path is a first-class path: everything falls through
      // to the agent and the run is still valid.
      continue;
    }

    for (const name of entries.slice().sort()) {
      if (!isProbeFile(name)) continue;
      const file = join(dir, name);
      // The same file reachable through two dir arguments is one probe.
      if (seenFiles.has(file)) continue;
      seenFiles.add(file);

      let mod: Record<string, unknown>;
      try {
        mod = (await import(pathToFileURL(file).href)) as Record<string, unknown>;
      } catch (e) {
        // Covers a syntax error, a throwing module body, and a missing import.
        warnings.push(`probe skipped: ${file} — failed to load: ${errText(e)}`);
        continue;
      }

      const exported = mod.default ?? mod.probe;
      if (exported === undefined) {
        warnings.push(
          `probe skipped: ${file} — no \`export default\` and no \`export const probe\``,
        );
        continue;
      }

      const problems = problemsWith(exported);
      if (problems.length > 0) {
        warnings.push(`probe skipped: ${file} — ${problems.join('; ')}`);
        continue;
      }

      const probe = exported as Probe;

      // Filename/metadata integrity. Non-fatal — the metadata is authoritative
      // and the filename is a convention — but never silent, because a probe
      // whose file says v2 and whose body says v1 will shadow the wrong thing.
      const m = VERSIONED_NAME.exec(name);
      if (m) {
        if (m[1] !== probe.id) {
          warnings.push(
            `probe ${file}: filename id "${m[1]}" disagrees with \`id\` "${probe.id}" — using \`id\``,
          );
        }
        if (Number(m[2]) !== probe.version) {
          warnings.push(
            `probe ${file}: filename version v${m[2]} disagrees with \`version\` ${probe.version} — using \`version\``,
          );
        }
      }

      candidates.push({ probe, file, dirIndex });
    }
  }

  // One id, one probe: highest version wins, later dir breaks a tie, and every
  // shadowed version is named. Insertion order of ids is preserved, so shipped
  // probes are still tried before runtime-minted ones.
  const byId = new Map<string, Candidate[]>();
  for (const c of candidates) {
    const list = byId.get(c.probe.id);
    if (list) list.push(c);
    else byId.set(c.probe.id, [c]);
  }

  const probes: Probe[] = [];
  for (const [id, list] of byId) {
    const ranked = list
      .slice()
      .sort((a, b) => b.probe.version - a.probe.version || b.dirIndex - a.dirIndex);
    const winner = ranked[0];
    probes.push(winner.probe);
    for (const loser of ranked.slice(1)) {
      warnings.push(
        `probe "${id}" v${loser.probe.version} at ${loser.file} is shadowed by v${winner.probe.version} at ${winner.file}`,
      );
    }
  }

  return { probes, warnings };
}
