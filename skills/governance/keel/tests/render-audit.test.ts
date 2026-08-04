/**
 * THE ε-AUDIT REPORTING TEST.
 *
 * `SKILL.md` §4 says the probe library's agreement rate is Keel's own
 * counter-metric and that a system refusing to measure its own groundedness is
 * telling you something. The number was computed, carried through the schema
 * (`Verdict.audit`), preserved by `corpus.ts` — and then dropped by the one
 * artifact a human actually reads. This file is the executed proof that it is
 * not dropped any more.
 *
 * EVERY assertion here runs the real `render()` over a real `Report` and reads
 * the bytes that come back. Nothing asserts that a template file contains a
 * substring: a template is an input, and a test that checks its inputs is
 * `self_referential` by this repo's own definition — it would keep passing
 * while `render.ts` stopped filling the block. The renderer is the system under
 * test, so the renderer is what gets executed.
 *
 * The reports are synthetic because they must be: no committed report carries
 * an `audit` block (that is the bug), and the three states that matter —
 * mixed, none, total disagreement — cannot all be sampled from one real run
 * anyway.
 */

import { describe, expect, test } from 'bun:test';
import { mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import type { GroundingClass, Node, Report, Verdict } from '../schemas/keel.ts';
import { groundingRatio } from '../schemas/keel.ts';
import { auditTally, loadTemplate, render } from '../scripts/render.ts';

// ---------------------------------------------------------------------------
// Builders. Deliberately minimal and deliberately valid: the point of each
// test below is the audit block, so every other field is well-formed enough
// that nothing else in the renderer can be the reason a string appears.
// ---------------------------------------------------------------------------

interface Spec {
  id: string;
  class: GroundingClass;
  decidedBy: 'probe' | 'agent';
  /** omit for "no ε-audit touched this verdict" */
  audit?: { agentClass: GroundingClass; agreed: boolean };
}

function nodeFor(spec: Spec, i: number): Node {
  return {
    id: spec.id,
    kind: 'ci_step',
    name: `step-${i}`,
    source: `.github/workflows/test.yml:${i + 10}`,
    raw: `- run: bun test  # ${spec.id}`,
  };
}

function verdictFor(spec: Spec): Verdict {
  const canWrite =
    spec.class === 'anchored' ? false : spec.class === 'self_referential' ? true : null;
  return {
    nodeId: spec.id,
    class: spec.class,
    writeBoundary: {
      producer: 'the bun test runner process exit code',
      actorCanWrite: canWrite,
      argument:
        'The exit code is produced by a runtime executing assertions on a runner the PR author does not control, so the actor cannot write to the producer.',
    },
    evidence: ['.github/workflows/test.yml:70', 'package.json#scripts.test'],
    confidence: 0.8,
    decidedBy: spec.decidedBy,
    ...(spec.decidedBy === 'probe' ? { probeId: 'probe-ci-exit-code@1' } : {}),
    ...(spec.audit
      ? { audit: { ...spec.audit, at: '2026-07-25T09:15:00.000Z' } }
      : {}),
  };
}

function reportOf(specs: Spec[]): Report {
  const nodes = specs.map(nodeFor);
  const verdicts = specs.map(verdictFor);
  const byProbe = verdicts.filter((v) => v.decidedBy === 'probe').length;
  return {
    target: 'github.com/broomva/keel',
    revision: 'c50e003',
    generatedAt: '2026-07-25T09:00:00.000Z',
    nodes,
    verdicts,
    grounding: groundingRatio(verdicts),
    economics: {
      nodesTotal: specs.length,
      nodesSampled: specs.length,
      decidedByProbe: byProbe,
      decidedByAgent: specs.length - byProbe,
      tokensIn: 4200,
      tokensOut: 900,
      tokensEstimated: true,
      wallClockMs: 12_400,
      probesMinted: 0,
      probeLibrarySize: byProbe > 0 ? 3 : 0,
    },
  };
}

/**
 * Strip tags so a prose assertion cannot be satisfied by an attribute value.
 * A tag becomes a space, so `(<span>75%</span>)` reads `( 75% )` — assertions
 * below allow for that rather than pretending the markup is not there.
 */
const textOf = (html: string): string =>
  html
    .replace(/<[^>]*>/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

/**
 * The ε-audit card only.
 *
 * The document inlines `tokens.css`, whose rgba alphas are decimals, so a
 * whole-document scan for "a number that looks like a rate" measures the
 * stylesheet. Scoping to the card is what makes "this state prints no rate" an
 * assertion about the claim rather than about the design system. The card
 * contains no nested `<div>`, so the first `</div>` after the marker closes it.
 */
function auditCardOf(html: string): string {
  const marker = html.indexOf('ε-audit');
  if (marker < 0) return '';
  const start = html.lastIndexOf('<div', marker);
  const end = html.indexOf('</div>', marker);
  return html.slice(start, end + '</div>'.length);
}

/** Every decimal in a slice that could be read as a rate. */
const ratesIn = (html: string): string[] => textOf(html).match(/\d+\.\d+/g) ?? [];

// ---------------------------------------------------------------------------

describe('render · a report with mixed agreement', () => {
  const report = reportOf([
    { id: 'a#1', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
    { id: 'a#2', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
    {
      id: 'a#3',
      class: 'anchored',
      decidedBy: 'probe',
      // The interesting one: the probe said anchored, the agent said the
      // signal is inside the write boundary.
      audit: { agentClass: 'self_referential', agreed: false },
    },
    { id: 'a#4', class: 'self_referential', decidedBy: 'probe' },
    { id: 'a#5', class: 'unknown', decidedBy: 'agent' },
  ]);
  const html = render(report);
  const text = textOf(html);

  test('both counts appear as absolute numbers, not only as a rate', () => {
    // 2 agreed of 3 compared. The pair is the deliverable — a bare 0.67 is the
    // same defect here as a bare grounding ratio.
    expect(text).toContain('2 / 3');
    expect(text).toMatch(/agreed \/ compared = 2 \/ 3/);
  });

  test('the rate is printed beside the counts, and it is the counted rate', () => {
    const a = auditTally(report.verdicts);
    expect(a).toMatchObject({ compared: 3, agreed: 2, disagreed: 1 });
    expect(text).toContain(`rate ${(a.agreed / a.compared).toFixed(2)}`);
    expect(text).toContain('rate 0.67');
  });

  test('the disagreement is present, counted, and marked as prominent', () => {
    expect(text).toContain('1 disagreement(s)');
    // Marked, not merely mentioned: the loud variant is a distinct element,
    // and the per-verdict row carries the grep-able attribute.
    expect(html).toContain('kr-audit-alert');
    expect(html).toContain('data-audit-disagreed');
    // Exactly one verdict row is flagged — the one whose audit disagreed.
    expect(html.match(/data-audit-disagreed/g)).toHaveLength(1);
  });

  test('the disagreeing verdict shows both classes: cached and re-decided', () => {
    // The whole value of a disagreement is knowing which way it went.
    const row = html.slice(html.indexOf('data-audit-disagreed'));
    const untilRowEnd = row.slice(0, row.indexOf('</p>'));
    expect(untilRowEnd).toContain('self_referential');
    expect(untilRowEnd).toContain('anchored');
  });

  test('an agreeing verdict shows its re-decided class without the alert', () => {
    // Two of the three audits agreed, so two quiet rows must be present...
    const quiet = text.match(/agent re-decided anchored\s*, agreed/g);
    expect(quiet).toHaveLength(2);
    // ...and the loud treatment must be reserved for the one that did not. If
    // the quiet variant ever borrowed the alert, prominence stops meaning
    // anything — so count the marker on verdict rows, not in the stylesheet.
    expect(html.match(/class="kr-line kr-audit-alert"/g)).toHaveLength(1);
  });

  test('audit coverage is stated in absolute terms, not implied', () => {
    // 4 probe-decided verdicts exist; 3 of them were audited.
    expect(text).toMatch(
      /Audit coverage — 3 of 4 probe-decided verdict\(s\) audited \(\s*75%\s*\)/,
    );
  });

  test('an audited verdict outside the probe population is disclosed, not folded in', () => {
    // All three audits here are probe-decided, so the disclosure must be absent
    // — the inverse case is covered below. This guards against a block that
    // renders unconditionally and reads as a caveat that does not apply.
    expect(text).not.toContain('audited verdict(s) were not probe-decided');
  });

  test('independence is not claimed anywhere in the output', () => {
    // `Report` carries no `mintedFrom`, so the renderer cannot know which
    // comparisons are independent. It must not say that it does.
    //
    // Round 1 of the cross-review noted the first form was narrow enough that
    // adding "these are independent comparisons" would pass. Round 2 noted the
    // second form still was: it dropped whole SENTENCES containing the
    // disclaimer, so a positive claim added to that same sentence vanished with
    // it. Counting occurrences has no such hiding place — every appearance of
    // "independen" in the document must BE the disclaimer.
    expect(text).toContain('not described as independent');
    const occurrences = text.match(/independen\w*/gi) ?? [];
    const disclaimers = text.match(/not described as independent/g) ?? [];
    expect(occurrences).toHaveLength(disclaimers.length);
    expect(disclaimers.length).toBeGreaterThan(0);
    expect(text).toContain('mintedFrom');
  });
});

describe('render · a report with zero audit blocks', () => {
  const report = reportOf([
    { id: 'b#1', class: 'anchored', decidedBy: 'probe' },
    { id: 'b#2', class: 'self_referential', decidedBy: 'probe' },
    { id: 'b#3', class: 'anchored', decidedBy: 'agent' },
  ]);
  const html = render(report);
  const text = textOf(html);

  test('the explicit no-audit state renders', () => {
    expect(auditTally(report.verdicts).compared).toBe(0);
    expect(text).toContain('ε-audit — not run');
    expect(text).toContain('there is no agreement rate to report');
  });

  test('it is not a rate: no fraction, no rate, and no number at all', () => {
    // The refusal, executed. Zero audited nodes must never read as agreement.
    expect(text).not.toMatch(/agreed \/ compared = /);
    expect(text).not.toMatch(/\brate \d/);
    expect(text).not.toContain('0 / 0');
    // The strongest available form: the card prints NO decimal whatsoever.
    // `1.00` is what a naive `agreed / compared` guard produces here and it is
    // the most flattering number in the file — but so is any other rate, and
    // even naming the forbidden one in prose would put it on the page.
    expect(ratesIn(auditCardOf(html))).toHaveLength(0);
    expect(auditCardOf(html)).not.toContain('1.00');
  });

  test('the un-audited population is named, so 0% coverage cannot hide', () => {
    // Audit coverage is shoppable: audit nothing, find nothing. The count of
    // what went un-audited is the disclosure that makes that visible.
    expect(text).toContain(
      '2 probe-decided verdict(s), none of them contributing a readable comparison',
    );
  });

  test('the grounding ratio still renders — the audit state is additive', () => {
    // A regression that made the no-audit branch swallow the page would pass
    // every assertion above.
    expect(text).toContain('anchored / (anchored + self_referential + unknown)');
    expect(html).toContain('k-ratio__value');
  });
});

describe('render · a report where every audited verdict disagreed', () => {
  // The inverse of the zero case, and the most valuable run the tool can have:
  // 0/N is a finding, not an absence, and it must not be swallowed by any
  // falsy-guard on the agreed count.
  const report = reportOf([
    { id: 'c#1', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'unknown', agreed: false } },
    { id: 'c#2', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'self_referential', agreed: false } },
  ]);
  const html = render(report);
  const text = textOf(html);

  test('it renders 0 / N as a measured result', () => {
    expect(auditTally(report.verdicts)).toMatchObject({ compared: 2, agreed: 0, disagreed: 2 });
    expect(text).toContain('0 / 2');
    expect(text).toContain('agreed / compared = 0 / 2');
    expect(text).toContain('rate 0.00');
  });

  test('0 / 2 is NOT rendered as the no-audit state', () => {
    // Total disagreement and no audit are opposite findings. Collapsing them
    // would lose the more informative one.
    expect(text).not.toContain('ε-audit — not run');
    expect(text).not.toContain('none of them audited');
  });

  test('every disagreeing verdict is individually marked', () => {
    expect(text).toContain('2 disagreement(s) recorded');
    expect(html.match(/data-audit-disagreed/g)).toHaveLength(2);
  });

  test('full coverage of the probe population is reported as 100%, not as agreement', () => {
    expect(text).toMatch(
      /Audit coverage — 2 of 2 probe-decided verdict\(s\) audited \(\s*100%\s*\)/,
    );
    // The trap this guards: 100% coverage sitting next to 0.00 agreement must
    // not be readable as a score. Both numbers, both meanings, side by side.
    expect(text).toContain('rate 0.00');
  });
});

describe('render · audits outside the probe population', () => {
  // An `audit` block on an agent-decided verdict is legal in the frozen schema.
  // It counts toward agreement (it IS a comparison) but it is not coverage of
  // the probe library, and conflating the two would inflate coverage.
  const report = reportOf([
    { id: 'd#1', class: 'anchored', decidedBy: 'agent', audit: { agentClass: 'anchored', agreed: true } },
    { id: 'd#2', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
    { id: 'd#3', class: 'self_referential', decidedBy: 'probe' },
  ]);
  const text = textOf(render(report));

  test('agreement counts the comparison; coverage does not', () => {
    expect(auditTally(report.verdicts)).toMatchObject({
      compared: 2,
      agreed: 2,
      probeDecided: 2,
      probeAudited: 1,
      auditedNonProbe: 1,
    });
    expect(text).toContain('agreed / compared = 2 / 2');
    expect(text).toMatch(
      /Audit coverage — 1 of 2 probe-decided verdict\(s\) audited \(\s*50%\s*\)/,
    );
  });

  test('the difference between the two denominators is stated out loud', () => {
    expect(text).toContain('sit on verdicts that were not probe-decided');
  });

  test('the probe library gets its OWN figure, not the pooled one', () => {
    // The cross-review's finding: a headline labelled "probe library agreement"
    // over a pooled population is a metric named after a population it does not
    // measure. The label now says "agreement", and the probe-only number is
    // printed where it is actually true.
    expect(text).toContain('ε-audit — agreement');
    expect(text).not.toContain('ε-audit — probe library agreement');
    expect(text).toMatch(/Probe-decided verdicts alone: 1 \/ 1 \(rate 1\.00\)/);
  });
});

describe('render · pooled agreement must not speak for the probe library', () => {
  // The exact input the cross-review named: one agent audit agrees, one probe
  // audit disagrees. Pooled reads 1/2; the probe library's own result is 0/1.
  // A reader must be able to see the second number, not infer it.
  const report = reportOf([
    { id: 'p#1', class: 'anchored', decidedBy: 'agent', audit: { agentClass: 'anchored', agreed: true } },
    { id: 'p#2', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'unknown', agreed: false } },
  ]);
  const text = textOf(render(report));

  test('both populations are reported, and neither borrows the other', () => {
    expect(auditTally(report.verdicts)).toMatchObject({
      compared: 2,
      agreed: 1,
      probeAudited: 1,
      probeAgreed: 0,
      auditedNonProbe: 1,
    });
    expect(text).toContain('agreed / compared = 1 / 2');   // pooled
    expect(text).toMatch(/Probe-decided verdicts alone: 0 \/ 1 \(rate 0\.00\)/);
    // The pooled rate must never be presented as the probe library's.
    expect(text).not.toMatch(/probe library[^.]*0\.50/i);
  });
});

describe('render · every comparison sits outside the probe population', () => {
  const report = reportOf([
    { id: 'q#1', class: 'anchored', decidedBy: 'agent', audit: { agentClass: 'anchored', agreed: true } },
    { id: 'q#2', class: 'anchored', decidedBy: 'probe' },
  ]);
  const text = textOf(render(report));

  test('no probe-library agreement is invented from agent-only comparisons', () => {
    expect(auditTally(report.verdicts)).toMatchObject({ compared: 1, probeAudited: 0 });
    expect(text).toContain('says nothing about the probe library');
    // 1/1 is true of the pooled figure and false of the probe library. The
    // probe-only line must not appear at all rather than print 1/0 or 0/0.
    expect(text).not.toMatch(/Probe-decided verdicts alone/);
  });
});

describe('render · the template must be complete at load time', () => {
  // The cross-review's third finding: a template missing an auxiliary block
  // loaded fine and failed later, on the one report shape that needed it.
  const AUXILIARY = [
    'audit-coverage',
    'audit-coverage-none',
    'audit-disagreement',
    'audit-nonprobe',
    'audit-nonprobe-only',
    'verdict-audit',
    'verdict-audit-disagreed',
    'audit-malformed',
    'verdict-audit-malformed',
  ];

  const TEMPLATE_PATH = join(
    import.meta.dir,
    '..', 'templates',
    'report.html',
  );
  const source = readFileSync(TEMPLATE_PATH, 'utf8');

  for (const block of AUXILIARY) {
    test(`loadTemplate refuses a template missing \`${block}\``, () => {
      // Delete the block from a COPY of the real template on disk and call the
      // real loader on it. This executes `loadTemplate`'s own required-list —
      // re-deriving the list inside the test would assert against a copy of the
      // thing under test, which is `self_referential` by this repo's definition
      // and would keep passing after someone shortened the real list.
      const stripped = source.replace(
        new RegExp(`<!--@block ${block}\\s*-->[\\s\\S]*?<!--@endblock\\s*-->`),
        '',
      );
      expect(stripped).not.toBe(source); // the block really was there to remove

      const tmp = join(mkdtempSync(join(tmpdir(), 'keel-tpl-')), 'report.html');
      writeFileSync(tmp, stripped);
      try {
        expect(() => loadTemplate(tmp)).toThrow(block);
      } finally {
        rmSync(dirname(tmp), { recursive: true, force: true });
      }
    });
  }

  test('the shipped template satisfies the whole required list', () => {
    expect(() => loadTemplate()).not.toThrow();
  });
});

describe('render · a report with no probe-decided verdicts at all', () => {
  const report = reportOf([
    { id: 'e#1', class: 'anchored', decidedBy: 'agent', audit: { agentClass: 'anchored', agreed: true } },
  ]);
  const text = textOf(render(report));

  test('coverage over an empty population is refused rather than printed', () => {
    // pct(0, 0) is 0 in this codebase, and "0% audited" would be a fabricated
    // claim about a population that does not exist.
    expect(text).toContain('no probe-decided verdict');
    expect(text).not.toMatch(/probe-decided verdict\(s\) audited \(\d+%\)/);
  });

  test('the agreement over the comparisons that DO exist still renders', () => {
    expect(text).toContain('agreed / compared = 1 / 1');
  });
});

describe('render · the artifact stays self-contained', () => {
  // The audit section adds markup to a document whose entire argument is that
  // it depends on nothing. `render()` throws on an off-origin reference before
  // returning, so reaching these assertions is already most of the proof —
  // they close the gap for shapes the guard does not match.
  // The embedding elements are here because the cross-review found they slipped
  // through a guard written around `src=`/`href=`: `<object data="https://…">`
  // and `<video poster="…">` both fetch on load through an attribute neither
  // pattern names. `render()` now refuses the tags outright and these assert it.
  const EXTERNAL = [
    /<script[^>]+\bsrc\s*=/i,
    /<link[^>]+\bhref\s*=/i,
    /@import\s+(?:url\(|["'])/i,
    /<img[^>]/i,
    /url\(\s*["']?https?:/i,
    /\bsrcset\s*=/i,
    /<(?:iframe|object|embed|video|audio|source|track)\b/i,
    /\bdata\s*=\s*["']https?:/i,
    /\bposter\s*=/i,
    /@font-face/i,
  ];

  for (const [label, report] of [
    [
      'with audit blocks',
      reportOf([
        { id: 'f#1', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'unknown', agreed: false } },
        { id: 'f#2', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
      ]),
    ],
    ['without audit blocks', reportOf([{ id: 'f#3', class: 'anchored', decidedBy: 'probe' }])],
  ] as const) {
    test(`a report ${label} issues zero external requests`, () => {
      const html = render(report);
      for (const pattern of EXTERNAL) {
        expect(html).not.toMatch(pattern);
      }
      // It must also open from file://: no protocol-relative or absolute-path
      // document reference anywhere in the markup.
      expect(html).not.toMatch(/(?:href|src)\s*=\s*["']\/\//i);
    });
  }

  test('the guard FIRES on an embedding element, rather than merely not seeing one', () => {
    // Asserting that clean output is clean proves the output, not the guard. A
    // guard that cannot fire is decoration — the same argument this repo makes
    // about SMELL_THRESHOLD. So: inject each offending element through the
    // template option and assert `render()` refuses to return it.
    const base = loadTemplate();
    // Every tag the guard names, not a sample of them — the round-2 review
    // pointed out that claiming seven and testing four leaves three untested.
    for (const offending of [
      '<object data="https://example.com/x.svg"></object>',
      '<embed src="https://example.com/x.swf">',
      '<iframe src="https://example.com"></iframe>',
      '<video poster="https://example.com/p.png"></video>',
      '<audio src="https://example.com/a.mp3"></audio>',
      '<source src="https://example.com/v.webm">',
      '<track src="https://example.com/c.vtt">',
      '<svg><image href="https://example.com/x.png"></image></svg>',
      '<meta http-equiv="refresh" content="0;url=https://example.com">',
    ]) {
      const sabotaged = { ...base, scope: `${base.scope}\n${offending}` };
      expect(() =>
        render(reportOf([{ id: 'x#1', class: 'anchored', decidedBy: 'probe' }]), {
          template: sabotaged,
        }),
      ).toThrow(/off-origin document reference/);
    }
  });

  test('a <style> block that fetches off-origin is refused', () => {
    // The tag guard cannot see this: `url(https://…)` inside CSS is a fetch
    // with no element attached. Asked only inside <style>, for the reason the
    // next test demonstrates.
    const base = loadTemplate();
    for (const css of [
      '.x{background-image:url(https://example.com/x.png)}',
      ".y{background:url('//example.com/y.png')}",
      '.z{background: URL( "https://example.com/z.png" )}',
    ]) {
      const sabotaged = { ...base, 'layout-css': `${base['layout-css']}\n${css}` };
      expect(() =>
        render(reportOf([{ id: 's#1', class: 'anchored', decidedBy: 'probe' }]), {
          template: sabotaged,
        }),
      ).toThrow(/off-origin/);
    }
  });

  test('every CSS fetch shape the review demonstrated is refused', () => {
    // Round 3 executed each of these through render() and got fetch-capable
    // HTML back. They are here as executed regressions, in both CSS positions.
    const base = loadTemplate();
    const CSS_FETCHES = [
      '.a{background-image:url(https://example.com/x.png)}',
      ".b{background:url('//example.com/y.png')}",           // protocol-relative
      '.c{background: URL( "https://example.com/z.png" )}',  // case + whitespace
      '.d{background-image:image-set("https://example.com/x.png" 1x)}',
      '.e{background-image:-webkit-image-set(url(//example.com/x.png) 1x)}',
      '@import url(https://example.com/x.css);',
      '@import "https://example.com/x.css";',
    ];
    for (const css of CSS_FETCHES) {
      // (a) inside a <style> block
      expect(() =>
        render(reportOf([{ id: 's#1', class: 'anchored', decidedBy: 'probe' }]), {
          template: { ...base, 'layout-css': `${base['layout-css']}\n${css}` },
        }),
      ).toThrow(/off-origin/);
    }
    // (b) inside a style="" attribute — a position the block scan cannot see.
    // Inner values are single-quoted because the attribute is double-quoted:
    // nesting `"` inside `"` is markup a browser mis-parses too, so asserting
    // against it would be testing a string that could never reach a renderer.
    for (const decl of [
      'background:url(https://example.com/x.png)',
      "background:url('//example.com/x.png')",
      "background-image:image-set('https://example.com/x.png' 1x)",
    ]) {
      expect(() =>
        render(reportOf([{ id: 's#2', class: 'anchored', decidedBy: 'probe' }]), {
          template: { ...base, scope: `<p style="${decl}">x</p>` },
        }),
      ).toThrow(/off-origin/);
    }
  });

  test('<img> is refused outright, including the shapes a src=https test misses', () => {
    const base = loadTemplate();
    for (const img of [
      '<img src="https://example.com/x.png">',
      '<img src="//example.com/x.png">',            // protocol-relative
      '<img srcset="https://example.com/x.png 1x">', // no src= at all
    ]) {
      expect(() =>
        render(reportOf([{ id: 'i#1', class: 'anchored', decidedBy: 'probe' }]), {
          template: { ...base, scope: img },
        }),
      ).toThrow(/off-origin/);
    }
  });

  test('a supplied curve is checked as a fragment, before it is spliced in', () => {
    // The curve is the only content inlined raw — `esc()` never touches it — so
    // it is the only way unescaped markup reaches the document. The final round
    // of the cross-review reached both remaining guard holes exclusively
    // through it. Checking the fragment on entry closes them at the boundary,
    // for every caller, not only the CLI path that went through `loadCurve`.
    const report = reportOf([{ id: 'c#9', class: 'anchored', decidedBy: 'probe' }]);
    for (const curve of [
      '<svg><rect style=fill:url(https://example.com/x.svg) /></svg>', // UNQUOTED attribute
      // image-set: the drift that made the SVG check and the CSS check
      // disagree — refused in a <style> block, allowed in an SVG, until the two
      // were given one definition of "this CSS fetches".
      '<svg><rect style=background-image:image-set(https://example.com/x.png) /></svg>',
      '<svg><image href="https://example.com/x.png"/></svg>',
      '<svg><style>@import url(https://example.com/x.css);</style></svg>',
      '<svg xlink:href="https://example.com/x"></svg>',
      '<svg><a href="//example.com/x"></a></svg>', // protocol-relative
    ]) {
      expect(() => render(report, { curveSvg: curve })).toThrow(/off-origin/);
    }
    // A self-contained curve is inlined, which is the whole point of the slot.
    const clean = '<svg viewBox="0 0 10 10"><path d="M0 0 L10 10"/></svg>';
    expect(render(report, { curveSvg: clean })).toContain(clean);
  });

  test('a data: URI image is not refused as "off-origin"', () => {
    // It fetches nothing — the bytes are in the document. Refusing it would
    // enforce self-containment against something already self-contained, and
    // say "off-origin" about bytes that never leave the file.
    const base = loadTemplate();
    const report = reportOf([{ id: 'd#9', class: 'anchored', decidedBy: 'probe' }]);
    const dataImg =
      '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" alt="">';
    expect(() => render(report, { template: { ...base, scope: dataImg } })).not.toThrow();
    // ...while every fetching spelling still is — including the COMPOSITION
    // the review found: a data: src is not a licence for the tag's other
    // fetching attribute. An exemption that inspects one attribute of a tag
    // that fetches through several is a hole, not an exemption.
    for (const img of [
      '<img src="https://example.com/x.png">',
      '<img src="//example.com/x.png">',
      '<img srcset="https://example.com/x.png 1x">',
      '<img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" srcset="https://example.com/x.png 1x">',
      '<img srcset="//example.com/x.png 1x" src="data:image/gif;base64,R0lGODlhAQABAAAAACw=">',
    ]) {
      expect(() =>
        render(report, { template: { ...base, scope: img } }),
      ).toThrow(/off-origin/);
    }
  });

  test('a target whose evidence contains `@import url(...)` still renders', () => {
    // Round 3's false-refusal finding, and the reason `@import` moved out of the
    // document-wide guard: a stylesheet is an ordinary thing for a repository to
    // contain, and refusing to render a valid report because the TARGET mentions
    // one is this tool's own named failure committed by the tool itself.
    const report = reportOf([{ id: 'u#1', class: 'anchored', decidedBy: 'probe' }]);
    (report.verdicts[0] as Verdict).evidence = [
      'app.css:1 — @import url(https://cdn.example.com/reset.css)',
    ];
    const html = render(report);
    expect(html).toContain('@import url(https://cdn.example.com/reset.css)');
  });

  test('a target whose own text contains url(https://…) still renders', () => {
    // The other half of the scoping decision, and the one that keeps the CSS
    // check from becoming a check that reads the target instead of the
    // document. `esc()` does not escape parentheses or colons, so this string
    // survives into the body verbatim — where it is inert text, not a fetch. A
    // document-wide scan would refuse this report for a URL its TARGET
    // mentioned, which is the exact failure mode Keel is named after.
    const report = reportOf([{ id: 't#1', class: 'anchored', decidedBy: 'probe' }]);
    // `evidence` is rendered verbatim into the body — `raw` is not, so putting
    // it there would prove nothing about what reaches the document.
    (report.verdicts[0] as Verdict).evidence = [
      'theme.css:12 — .hero{background-image:url(https://cdn.example.com/hero.png)}',
    ];
    const html = render(report);
    expect(html).toContain('url(https://cdn.example.com/hero.png)');
  });

  test('a target snippet that MENTIONS such an element is not refused', () => {
    // The other half, and the one that makes the guard a real check rather than
    // one that fires on the data it measures: gathered `raw` text routinely
    // contains markup, and `esc()` neutralises it long before the guard runs.
    // If this ever throws, the guard has started reading the target instead of
    // the document.
    const report = reportOf([{ id: 'y#1', class: 'anchored', decidedBy: 'probe' }]);
    (report.nodes[0] as Node).raw = '<object data="https://example.com/x"></object>';
    (report.nodes[0] as Node).name = '<iframe src="https://example.com">';
    expect(() => render(report)).not.toThrow();
  });

  test('no unfilled slot survives into either output', () => {
    // `fill()` throws on a slot it was not given a value for, but a slot in a
    // block nobody filled would ship silently. This reads the bytes.
    for (const report of [
      reportOf([{ id: 'g#1', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } }]),
      reportOf([{ id: 'g#2', class: 'anchored', decidedBy: 'probe' }]),
      reportOf([]),
    ]) {
      const html = render(report);
      expect(html).not.toMatch(/\{\{\s*[A-Z_]+\s*\}\}/);
    }
  });
});

describe('render · the tally is arithmetic over what the verdicts carry', () => {
  test('an empty report audits nothing and claims nothing', () => {
    const html = render(reportOf([]));
    expect(auditTally([])).toMatchObject({ compared: 0, agreed: 0, probeDecided: 0 });
    expect(textOf(html)).toContain('ε-audit — not run');
    expect(ratesIn(auditCardOf(html))).toHaveLength(0);
  });

  test('the rendered counts equal a recomputation over the same verdicts', () => {
    // The renderer must not carry a second, drifting notion of what agreed.
    const report = reportOf([
      { id: 'h#1', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
      { id: 'h#2', class: 'unknown', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: false } },
      { id: 'h#3', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
    ]);
    const expected = report.verdicts.filter((v) => v.audit?.agreed === true).length;
    const compared = report.verdicts.filter((v) => v.audit !== undefined).length;
    expect(textOf(render(report))).toContain(`agreed / compared = ${expected} / ${compared}`);
  });
});

// ---------------------------------------------------------------------------
// Malformed audit blocks.
//
// These bypass the `Spec` builders on purpose. `Spec.audit` is typed to a valid
// `GroundingClass` plus a boolean, so a well-typed producer cannot express any
// of the shapes below — and every one of them is reachable from JSON, which is
// how a `Report` actually arrives. The renderer's job is to refuse them.
//
// The direction is the whole point. `{agreed: true}` with no `agentClass` names
// no re-decided class, so no comparison happened; counting it as agreement lets
// a verdict assert its own audit passed, on the one number that exists to catch
// a claim standing in for a check. Counting it as a disagreement is equally
// false and additionally unshowable: the per-verdict branch has no class to
// print, so the summary would claim a disagreement no row can be found for.
// ---------------------------------------------------------------------------

/** A report whose single probe-decided verdict carries `audit` verbatim. */
function reportWithRawAudit(audit: unknown): Report {
  const report = reportOf([{ id: 'n1', class: 'anchored', decidedBy: 'probe' }]);
  (report.verdicts[0] as unknown as Record<string, unknown>).audit = audit;
  return report;
}

const MALFORMED: Array<[string, unknown]> = [
  ['agreed:true with no agentClass', { agreed: true, at: 'x' }],
  ['agreed:true with a garbage agentClass', { agentClass: 'totally_fine', agreed: true, at: 'x' }],
  ['agreed as a truthy string', { agentClass: 'anchored', agreed: 'yes', at: 'x' }],
  ['agreed as 1', { agentClass: 'anchored', agreed: 1, at: 'x' }],
  ['audit: null', null],
  ['audit as a bare string', 'audited'],
  // `at` is required by the frozen schema. Without this, the card printed
  // `1 / 1 · rate 1.00` above a per-verdict row whose timestamp read the
  // literal text `undefined` — a perfect score over a record that cannot say
  // when it was made.
  ['no `at` at all', { agentClass: 'anchored', agreed: true }],
  ['`at` as a number', { agentClass: 'anchored', agreed: true, at: 7 }],
  ['`at` blank', { agentClass: 'anchored', agreed: true, at: '   ' }],
  // Self-contradictory records. The verdict under test is `anchored`, so:
  // "agreed" while naming a DIFFERENT class would hide a real disagreement
  // inside the agreement count, and "disagreed" while naming the SAME class
  // makes the artifact's own sentence ("the two classes differ, one of them is
  // wrong") false on a row where they are identical.
  ['agreed:true naming a different class', { agentClass: 'unknown', agreed: true, at: 'x' }],
  ['agreed:false naming the same class', { agentClass: 'anchored', agreed: false, at: 'x' }],
];

describe('a malformed audit block is never agreement', () => {
  for (const [label, audit] of MALFORMED) {
    test(`${label} — excluded from the denominator, not counted as agreement`, () => {
      const report = reportWithRawAudit(audit);
      const tally = auditTally(report.verdicts);
      expect(tally.compared).toBe(0);
      expect(tally.agreed).toBe(0);
      expect(tally.disagreed).toBe(0);
      expect(tally.malformed).toBe(1);

      // Zero WELL-FORMED comparisons is the not-run state, whatever arrived
      // alongside — so no rate at all, and specifically not the flattering one.
      // Asserted on the audit card's OWN strings: a bare `1 / 1` also occurs in
      // the ratio formula and in "nodes judged / gathered", so matching that
      // would fail for reasons having nothing to do with this feature.
      const text = textOf(render(report));
      expect(text).toContain('ε-audit — not run');
      expect(text).not.toContain('agreed / compared');
      expect(text).not.toMatch(/rate \d/);
    });

    test(`${label} — disclosed, never silently dropped`, () => {
      const text = textOf(render(reportWithRawAudit(audit)));
      expect(text).toContain('could not be read');
      // And it must not be dressed up as a finding about the target.
      expect(text).toContain('defect in whatever wrote the report');
    });

    test(`${label} — the verdict row says unreadable, not disagreement`, () => {
      const html = render(reportWithRawAudit(audit));
      expect(html).toContain('data-audit-malformed');
      expect(html).not.toContain('data-audit-disagreed');
      expect(textOf(html)).toContain('ε-audit block unreadable');
    });
  }

  test('a summary disagreement count always has a row a reader can find', () => {
    // The regression that motivated this: `audit: null` reported "1
    // disagreement(s)" while zero verdicts carried the marker, so the reader was
    // told about a disagreement that could not be located.
    for (const [, audit] of MALFORMED) {
      const html = render(reportWithRawAudit(audit));
      const claimed = /(\d+) disagreement\(s\) recorded/.exec(textOf(html));
      const marked = (html.match(/data-audit-disagreed/g) ?? []).length;
      expect(marked).toBe(claimed ? Number(claimed[1]) : 0);
    }
  });

  test('a well-formed block alongside a malformed one still counts, alone', () => {
    const report = reportOf([
      { id: 'good', class: 'anchored', decidedBy: 'probe', audit: { agentClass: 'anchored', agreed: true } },
      { id: 'bad', class: 'anchored', decidedBy: 'probe' },
    ]);
    (report.verdicts[1] as unknown as Record<string, unknown>).audit = { agreed: true };
    const tally = auditTally(report.verdicts);
    expect(tally.compared).toBe(1);
    expect(tally.agreed).toBe(1);
    expect(tally.malformed).toBe(1);
    const text = textOf(render(report));
    // The rate is over the ONE readable comparison, not inflated to 2/2.
    expect(text).toContain('agreed / compared = 1 / 1');
    expect(text).toContain('could not be read');
  });
});
