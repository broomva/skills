/**
 * THE EFFORT-VOCABULARY TEST.
 *
 * `effort` is the key `rankBindings` sorts by, and "cheapest fix first" is the
 * entire point of that ordering. It is also an enum, and an enum is only usable
 * by an agent that can discover its legal values. This file is the executed
 * proof that it can.
 *
 * The bug this was written against: the values lived in exactly one place —
 * a type declaration in `schemas/route.ts` — and appeared neither in the
 * `--dispatch` payload the agent is told to judge from nor in `SKILL.md`. An
 * agent followed the documented three-step shape, authored `"effort": "low"`,
 * and the field was warned about and dropped. Correct fail-safe behaviour, and
 * a silently unranked result: the drop is loud on stderr and invisible in the
 * artifact.
 *
 * Every test here EXECUTES the real CLI — `bun route.ts --dispatch` and
 * `bun route.ts --proposals` as separate processes, over the real fixture
 * report. Nothing asserts a constant. In particular there is deliberately no
 * assertion that the enum equals `['config','wiring','process']`: that would
 * assert a constant against itself, which is `self_referential` by this repo's
 * own rubric and would be worthless as evidence for the claim being made.
 *
 * The claim being made is a RELATION between two runtime-derived lists:
 *
 *   the values the dispatch ADVERTISES  ===  the values the validator ACCEPTS
 *
 * Both sides are read out of the running program — the first from the emitted
 * dispatch JSON, the second parsed back out of the validator's own rejection
 * message. The test fails the moment those two drift apart, which is exactly
 * the bug class above, and it would have caught the original finding.
 */

import { describe, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { EFFORT_ORDER, ROUTE_EFFORTS } from '../schemas/route.ts';
import { bind, buildDispatch } from '../scripts/route.ts';

const ROUTE = resolve(import.meta.dir, '../scripts/route.ts');
const FIXTURE = resolve(import.meta.dir, 'fixtures/report.sample.json');

interface Run {
  code: number;
  stdout: string;
  stderr: string;
}

/** Run the real CLI as a child process, exactly as a caller would. */
function runRoute(args: string[]): Run {
  const p = Bun.spawnSync(['bun', ROUTE, FIXTURE, ...args]);
  return {
    code: p.exitCode,
    stdout: new TextDecoder().decode(p.stdout),
    stderr: new TextDecoder().decode(p.stderr),
  };
}

interface EffortOption {
  value: string;
  means: string;
}

function dispatch(): {
  effortValues: EffortOption[];
  requests: { node: { id: string } }[];
  anchoredIds: string[];
} {
  const r = runRoute(['--dispatch']);
  // Only the exit code is under assertion; stderr rides along so a failure
  // shows what the CLI actually said instead of just "expected 0, got 1".
  expect({ code: r.code, stderr: r.stderr }).toMatchObject({ code: 0 });
  return JSON.parse(r.stdout);
}

/** Drive proposals through the validator and read back what survived. */
function propose(proposals: unknown[]): {
  bindings: { loop: string; effort?: string; anchoredOn: string | null }[];
  stderr: string;
  code: number;
} {
  const dir = mkdtempSync(join(tmpdir(), 'keel-effort-'));
  try {
    const path = join(dir, 'proposals.json');
    writeFileSync(path, JSON.stringify(proposals, null, 2));
    const r = runRoute(['--proposals', path]);
    return { bindings: JSON.parse(r.stdout).bindings, stderr: r.stderr, code: r.code };
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

describe('the effort vocabulary reaches the agent that has to author it', () => {
  test('--dispatch carries the legal values, each with the distinction that makes it choosable', () => {
    const d = dispatch();

    // Non-vacuous: there is actually someone to tell. A dispatch with no
    // requests would make advertising the vocabulary moot.
    expect(d.requests.length).toBeGreaterThan(0);
    expect(d.anchoredIds.length).toBeGreaterThan(0);

    expect(Array.isArray(d.effortValues)).toBe(true);
    expect(d.effortValues.length).toBeGreaterThan(0);

    for (const e of d.effortValues) {
      expect([e.value, typeof e.value]).toEqual([e.value, 'string']);
      expect(e.value.trim()).not.toBe('');
      // The semantics travel with the value. A bare token says what is legal
      // but not how to choose, and choosing is the judgment being asked for.
      expect([e.value, typeof e.means]).toEqual([e.value, 'string']);
      expect([e.value, e.means.trim() === '']).toEqual([e.value, false]);
    }

    // A vocabulary that says the same thing three times does not help anyone
    // choose, so the values and their meanings must both be distinct.
    const values = d.effortValues.map((e) => e.value);
    const means = d.effortValues.map((e) => e.means);
    expect(new Set(values).size).toBe(values.length);
    expect(new Set(means).size).toBe(means.length);
  });

  test('every value the dispatch advertises survives --proposals — advertised is accepted', () => {
    const d = dispatch();
    const advertised = d.effortValues.map((e) => e.value);
    const anchor = d.anchoredIds[0] as string;
    const loops = d.requests.map((r) => r.node.id);

    // One advertised value per distinct node, so a single node's rejection
    // cannot mask another's acceptance.
    expect(loops.length).toBeGreaterThanOrEqual(advertised.length);
    const proposals = advertised.map((effort, i) => ({
      loop: loops[i],
      anchoredOn: anchor,
      argument: 'the signal is produced by the runner, which the author cannot author',
      effort,
    }));

    const { bindings, stderr, code } = propose(proposals);
    expect(code).toBe(0);

    for (const [i, effort] of advertised.entries()) {
      const b = bindings.find((x) => x.loop === loops[i]);
      // The route resolved, so `effort` is not stripped for being on a null
      // route — the only thing under test here is the vocabulary.
      expect([effort, b?.anchoredOn]).toEqual([effort, anchor]);
      expect([effort, b?.effort]).toEqual([effort, effort]);
    }
    // Not one advertised value was rejected as illegal.
    expect(stderr).not.toContain('— dropped, so this route ranks last');
  });

  test('the accept-list the validator names is the list the dispatch advertises', () => {
    const d = dispatch();
    const advertised = d.effortValues.map((e) => e.value);
    const loop = d.requests[0]?.node.id as string;

    // The rejection message names the accept-list, so the validator's own
    // vocabulary can be read back out of the running program rather than
    // restated here as a constant.
    const { stderr } = propose([
      {
        loop,
        anchoredOn: d.anchoredIds[0],
        argument: 'the exit code comes from the runner',
        effort: 'definitely-not-a-legal-effort',
      },
    ]);

    const m = stderr.match(/which is not (.+?) — dropped/);
    expect([stderr, m === null]).toEqual([stderr, false]);
    const accepted = (m as RegExpMatchArray)[1].split('|');

    expect(accepted.length).toBeGreaterThan(0);
    expect([...accepted].sort()).toEqual([...advertised].sort());
  });

  test('an unrecognised effort warns, drops, and does not throw', () => {
    const d = dispatch();
    const loop = d.requests[0]?.node.id as string;
    const anchor = d.anchoredIds[0] as string;

    // `low` is the literal value from the dogfood finding.
    const { bindings, stderr, code } = propose([
      {
        loop,
        anchoredOn: anchor,
        argument: 'the exit code comes from the runner, which the author cannot author',
        effort: 'low',
      },
    ]);

    // Did not throw: the process exited cleanly and still emitted a parseable
    // artifact. Fail-safe, not fail-stop.
    expect(code).toBe(0);
    expect(bindings.length).toBeGreaterThan(0);

    const b = bindings.find((x) => x.loop === loop);
    // The rest of the proposal survived — only `effort` was refused.
    expect(b?.anchoredOn).toBe(anchor);
    // Dropped, and NOT coerced. Inventing `config` because the agent said
    // `low` is a judgment plumbing may not make, and it would silently corrupt
    // the ordering this field exists to produce.
    expect(b?.effort).toBeUndefined();

    // Warned, naming the node and the value it refused.
    expect(stderr).toContain(loop);
    expect(stderr).toContain('low');
  });

  test('a present-but-invalid effort of any type warns and drops — not just strings', () => {
    const d = dispatch();
    const loop = d.requests[0]?.node.id as string;
    const anchor = d.anchoredIds[0] as string;
    const argument = 'the exit code comes from the runner, which the author cannot author';

    // The validator once gated on `typeof effort === 'string'`, so everything
    // here except `"low"` was dropped in TOTAL silence — no warning, no
    // ranking, no trace. A silent drop is the failure this whole change exists
    // to stop, so every present-but-illegal shape has to be named out loud.
    const illegal: unknown[] = [42, true, false, null, {}, [], ['config'], 3.5];

    for (const effort of illegal) {
      const label = JSON.stringify(effort) ?? String(effort);
      const { bindings, stderr, code } = propose([
        { loop, anchoredOn: anchor, argument, effort },
      ]);
      expect([label, code]).toEqual([label, 0]);
      const b = bindings.find((x) => x.loop === loop);
      // Route survives, effort refused, nothing coerced to a default.
      expect([label, b?.anchoredOn]).toEqual([label, anchor]);
      expect([label, b?.effort]).toEqual([label, undefined]);
      // Named out loud, for this node.
      expect([label, stderr.includes(loop)]).toEqual([label, true]);
      expect([label, /which is not .+ — dropped/.test(stderr)]).toEqual([label, true]);
    }

    // Non-vacuous the other way: an ABSENT effort is legal and must stay quiet,
    // otherwise the assertions above would pass for a validator that simply
    // warns about everything.
    const absent = propose([{ loop, anchoredOn: anchor, argument }]);
    expect(absent.stderr).not.toMatch(/which is not .+ — dropped/);
    expect(absent.bindings.find((x) => x.loop === loop)?.effort).toBeUndefined();
  });

  test('the values an agent is most likely to guess are refused, and none is normalised in', () => {
    const d = dispatch();
    const legal = new Set(d.effortValues.map((e) => e.value));
    const loop = d.requests[0]?.node.id as string;
    const anchor = d.anchoredIds[0] as string;
    const argument = 'the artifact is produced by a step the author does not control';

    // `low` is the value from the dogfood finding; the rest are the adjacent
    // guesses an agent reaches for when a vocabulary is undiscoverable, plus
    // case and whitespace variants of the legal values themselves — those
    // catch a validator that quietly normalises instead of refusing.
    const guesses = [
      'low',
      'medium',
      'high',
      'easy',
      'trivial',
      'small',
      'cheap',
      'manual',
      '',
      ...d.effortValues.map((e) => e.value.toUpperCase()),
      ...d.effortValues.map((e) => ` ${e.value} `),
    ].filter((g) => !legal.has(g));

    expect(guesses.length).toBeGreaterThan(8);

    for (const effort of guesses) {
      const { bindings } = propose([{ loop, anchoredOn: anchor, argument, effort }]);
      const b = bindings.find((x) => x.loop === loop);
      // Sampled, and the claim is scoped to the sample: none of THESE is
      // accepted, and none is silently normalised into a legal value. Nothing
      // here establishes closure over all strings, and the accept-list test
      // above does not either — it compares the list the validator NAMES to
      // the list the dispatch advertises, which a validator quietly accepting
      // some unsampled fourth value would still pass. That residue is real and
      // is left stated rather than dressed up: what is proven is that every
      // advertised value works and that the guesses agents actually make fail.
      expect([effort, b?.effort]).toEqual([effort, undefined]);
    }
  });

  test("SKILL.md's effort table is the dispatch vocabulary, in order, with the same meanings", () => {
    const d = dispatch();
    const skill = readFileSync(
      resolve(import.meta.dir, '../SKILL.md'),
      'utf8',
    );
    expect(skill.length).toBeGreaterThan(1000);

    // Locate the TABLE, not the tokens. Searching the whole file for `config`
    // would pass with the table deleted and the word surviving in a sentence
    // somewhere else, which is documentation drift wearing a green check —
    // the same shape as the bug this file was written against.
    const lines = skill.split('\n');
    const head = lines.findIndex((l) => /^\|\s*`effort`\s*\|\s*means\s*\|/.test(l));
    expect([head, head >= 0]).toEqual([head, true]);
    expect(lines[head + 1]).toMatch(/^\|\s*-+\s*\|/);

    const documented: { value: string; means: string }[] = [];
    for (const line of lines.slice(head + 2)) {
      if (!line.startsWith('|')) break;
      const m = line.match(/^\|\s*`([^`]+)`\s*\|\s*(.+?)\s*\|\s*$/);
      expect([line, m === null]).toEqual([line, false]);
      const row = m as RegExpMatchArray;
      documented.push({ value: row[1], means: row[2] });
    }

    // Prose drops the sentence-final period the payload carries; nothing else
    // may differ. Normalising more than that would let the two texts diverge
    // in meaning while still comparing equal.
    const norm = (s: string) => s.trim().replace(/\.$/, '').replace(/\s+/g, ' ');

    // Ordered: the table is the reader's cheapest-first ranking, so a table
    // that listed `process` before `config` would teach the wrong order even
    // with every value present.
    expect(documented.map((r) => r.value)).toEqual(d.effortValues.map((e) => e.value));
    expect(documented.map((r) => norm(r.means))).toEqual(
      d.effortValues.map((e) => norm(e.means)),
    );
  });

  // Scope note: what is frozen is the shared TABLE and its entries — the thing
  // every dispatch hands out by reference, and the only path by which one
  // consumer's write could change what a later caller advertises. Replacing the
  // `effortValues` property on a dispatch object a caller already owns is not
  // prevented and is not claimed to be; that mutates one local object and
  // reaches nothing else.
  test('the advertised table and its entries refuse writes, so no consumer can retune the vocabulary', () => {
    // Built IN-PROCESS on purpose. The CLI helper above round-trips through a
    // subprocess and `JSON.parse`, which hands back a fresh mutable copy every
    // time — attacking that would prove nothing about what `buildDispatch`
    // actually exposes. This is the object a same-process consumer holds.
    const report = JSON.parse(readFileSync(FIXTURE, 'utf8'));
    const d = buildDispatch(report, FIXTURE);
    const before = d.effortValues.map((e) => e.value);
    expect(before.length).toBeGreaterThan(0);

    // `as const` is a compile-time claim and stops nothing here, so the
    // single-source promise is only true if the runtime object refuses writes.
    // Otherwise a consumer could make the payload advertise a value the
    // validator still refuses — precisely the drift this design claims to have
    // eliminated, reintroduced through the reference it hands out.
    const live = d.effortValues as unknown as EffortOption[];
    expect(() => live.push({ value: 'mutated', means: 'x' })).toThrow(TypeError);
    expect(() => {
      live[0].value = 'mutated';
    }).toThrow(TypeError);

    expect(Object.isFrozen(d.effortValues)).toBe(true);
    expect(d.effortValues.every((e) => Object.isFrozen(e))).toBe(true);
    expect(d.effortValues.map((e) => e.value)).toEqual(before);

    // The rank map is derived from that table and is what `rankBindings`
    // reads, so it inherits the same guarantee — a writable rank would
    // reorder every page while the payload still advertised cheapest-first.
    expect(Object.isFrozen(EFFORT_ORDER)).toBe(true);
    expect(() => {
      (EFFORT_ORDER as unknown as Record<string, number>).config = 99;
    }).toThrow(TypeError);
    expect(ROUTE_EFFORTS.map((e) => EFFORT_ORDER[e.value])).toEqual(
      ROUTE_EFFORTS.map((_, i) => i),
    );
  });

  test('a dropped effort costs the ranking, which is what the warning says it does', () => {
    const d = dispatch();
    const anchor = d.anchoredIds[0] as string;
    const loops = [...d.requests.map((r) => r.node.id)].sort();

    // The valid proposal goes on the node that sorts LAST by id and the
    // invalid one on the node that sorts FIRST, so ranking by id alone would
    // put them the other way round. Only `effort` can produce this order.
    const cheap = loops[loops.length - 1] as string;
    const dropped = loops[0] as string;
    const cheapest = d.effortValues[0]?.value as string;

    const argument = 'the artifact is produced by a step the author does not control';
    const { bindings } = propose([
      { loop: cheap, anchoredOn: anchor, argument, effort: cheapest },
      { loop: dropped, anchoredOn: anchor, argument, effort: 'low' },
    ]);

    const iCheap = bindings.findIndex((b) => b.loop === cheap);
    const iDropped = bindings.findIndex((b) => b.loop === dropped);
    expect(iCheap).toBeGreaterThanOrEqual(0);
    expect(iDropped).toBeGreaterThanOrEqual(0);

    // Both routed, so both sit in the routable group and the only thing
    // separating them is the effort that survived versus the one that did not.
    expect(bindings[iCheap]?.anchoredOn).toBe(anchor);
    expect(bindings[iDropped]?.anchoredOn).toBe(anchor);
    expect(bindings[iCheap]?.effort).toBe(cheapest);
    expect(bindings[iDropped]?.effort).toBeUndefined();

    expect(iCheap).toBeLessThan(iDropped);
  });
});

// ---------------------------------------------------------------------------
// An effort nobody authored must not rank a route.
//
// These call `bind` IN-PROCESS on purpose. The helpers above spawn the CLI as a
// child, and a polluted `Object.prototype` in this process does not cross that
// boundary — a child-process test would pass while the defect sat untouched.
// `bind` is exported and runs in whatever process the host provides, which is
// exactly the situation this guards.
//
// Reading `p.effort` with `!== undefined` walked the prototype chain, so under
// an ambient `Object.prototype.effort` a proposal that declared no effort
// acquired one and was ranked by it, silently. Same defect class as a verdict
// nobody argued: a value arriving from outside the record, treated as part of
// it.
// ---------------------------------------------------------------------------

describe('only an effort the proposal itself declares is honoured', () => {
  const report = JSON.parse(readFileSync(FIXTURE, 'utf8'));
  const d = dispatch();
  const loop = d.requests[0]?.node.id as string;
  const anchor = d.anchoredIds[0] as string;
  const ARG = 'the anchor is an exit code the PR author cannot write to';

  /** Run `bind` with `Object.prototype.effort` set, always restoring it. */
  function bindUnderPollution(proposals: unknown[], polluted: unknown) {
    try {
      (Object.prototype as Record<string, unknown>).effort = polluted;
      return bind(report, proposals as never, { sourceReport: 'r.json' });
    } finally {
      delete (Object.prototype as Record<string, unknown>).effort;
    }
  }

  for (const polluted of ['process', 'config', 'nonsense', null]) {
    test(`Object.prototype.effort = ${JSON.stringify(polluted)} does not reach a binding`, () => {
      const out = bindUnderPollution(
        [{ loop, anchoredOn: anchor, argument: ARG }],
        polluted,
      );
      // Absent stays absent: not inherited, not defaulted, and not warned
      // about — a warning would itself be a claim that the agent said something.
      expect(out.bindings[0]?.effort).toBeUndefined();
      expect(out.warnings.filter((w: string) => w.includes('effort'))).toHaveLength(0);
    });
  }

  test('a declared effort still wins while the prototype carries another', () => {
    const out = bindUnderPollution(
      [{ loop, anchoredOn: anchor, effort: 'config', argument: ARG }],
      'process',
    );
    expect(out.bindings[0]?.effort).toBe('config');
  });

  test('an own effort of undefined is absent, not present-and-invalid', () => {
    const out = bindUnderPollution(
      [{ loop, anchoredOn: anchor, effort: undefined, argument: ARG }],
      'process',
    );
    expect(out.bindings[0]?.effort).toBeUndefined();
    expect(out.warnings.filter((w: string) => w.includes('effort'))).toHaveLength(0);
  });
});
