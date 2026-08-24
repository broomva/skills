#!/usr/bin/env bun
/**
 * Keel — report renderer.
 *
 *   bun scripts/render.ts <report.json> [-o out.html] [--curve reports/curve.svg]
 *
 * One `report.json` in, one self-contained HTML file out: inline styles, inline
 * marks, zero external requests. It has to open from `file://` and survive
 * being emailed, so nothing here may reference a CDN, a webfont, or an image
 * host — the artifact's argument is that it depends on nothing, and an artifact
 * that fetches a stylesheet to make that argument has already lost it.
 *
 * WHAT THIS FILE IS ALLOWED TO DO. It locates, loads, and renders. It contains
 * no judgment: no map from a check name to a `GroundingClass`, no heuristic
 * that promotes a node, no default class. Every class shown here was decided
 * upstream by a probe or an agent and arrives in the report. The one number
 * this file computes is the ratio, and it computes it by calling the frozen
 * schema's `groundingRatio` over the report's own verdicts — then prints a
 * disclosure if that disagrees with the ratio the report carried, rather than
 * trusting a field the producer could have written by hand.
 *
 * THE FIVE REFUSALS, all of them load-bearing:
 *   - a ratio never renders alone (absolute anchored count, coverage by kind,
 *     and the raw counts sit beside it, always),
 *   - `not_a_check` prints beside the fraction, never inside it,
 *   - zero gathered nodes renders "nothing gathered", never 0.00,
 *   - an empty denominator renders "no denominator", never 0.00,
 *   - zero ε-audit comparisons renders "not run", never an agreement rate and
 *     never 1.00.
 * The last three matter most: a printed number reads as a measurement, and
 * none of those states measured anything.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import type { GroundingClass, Node, Report, Verdict } from '../schemas/keel.ts';
import { coverageByKind, groundingRatio } from '../schemas/keel.ts';
import type { GatherCoverage } from './gather.ts';

// ---------------------------------------------------------------------------
// Constants that encode a ruling, each with the ruling attached.
// ---------------------------------------------------------------------------

/**
 * An `anchored` verdict asserted below this confidence is flagged.
 *
 * The design system's prose says 0.5; the orchestrator raised it to 0.6 on the
 * evidence that a real, adversarially-reviewed run bottoms out at exactly 0.50,
 * so a strict `< 0.5` test can never fire on honest data — a smell detector
 * that cannot fire is decoration. The threshold is printed in the artifact
 * rather than left implicit here, because a reader cannot audit a number they
 * cannot see.
 */
const SMELL_THRESHOLD = 0.6;

/** Schema order. Rendering order for sections, counts, the meter and the legend. */
const CLASS_ORDER: GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
  'not_a_check',
];

/** Classes inside the denominator. `not_a_check` is deliberately absent. */
const DENOMINATOR_CLASSES: GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
];

const CLASS_NOTE: Record<GroundingClass, string> = {
  anchored:
    'The producer sits outside the write boundary of the actor being verified.',
  self_referential:
    'The producer sits inside the write boundary of the actor being verified.',
  unknown:
    'The fork point could not be established. Fails closed — counts against the ratio exactly like self_referential.',
  not_a_check:
    'Asserts nothing about correctness, so it is excluded from the denominator. This is the one shoppable class: mis-filing a real check here shrinks the denominator and inflates the score, so each row carries the same burden of argument as any other verdict.',
};

/**
 * Off-origin document references. This is the acceptance assertion, executed
 * on our own output before it is written: content may legitimately *mention* a
 * URL (a gathered `raw` snippet routinely does), but the DOCUMENT must fetch
 * nothing. Matching on fetch-shaped markup rather than on the substring
 * "https://" is the difference between a real check and one that fires on the
 * data it is measuring.
 *
 * `@import` is matched as an at-RULE (`@import url(` / `@import "`), not as the
 * word: `tokens.css` explains in a comment why the system is one file and not
 * five "behind an @import entry point", and a check that fires on that sentence
 * is measuring its own prose. This renderer's entire subject is checks that
 * read something other than what they claim to read, so the distinction is not
 * a convenience.
 *
 * The embedding elements (`object`, `embed`, `iframe`, `video`, `audio`,
 * `source`, `track`) are refused on the TAG, with no URL test, because the
 * cross-review found they slipped through a guard written around `src=` and
 * `href=`: an `<object data="https://…">` or a `<video poster="…">` fetches on
 * load through an attribute neither pattern names. Enumerating their attributes
 * would just move the hole, and this artifact has no legitimate use for any of
 * them — a document whose argument is that it depends on nothing does not embed
 * a subdocument. Gathered target text cannot trip this: `esc()` turns a snippet
 * containing `<object` into `&lt;object` long before the guard runs.
 *
 * `<img>` is the one exception, and it is narrow in both directions. A
 * `src="data:…"` image is carried IN the document and fetches nothing, so
 * refusing it would enforce self-containment against something already
 * self-contained — and the error would say "off-origin" about bytes that never
 * leave the file. Every other `<img>` is refused, `src=` or not, because
 * `srcset` and a protocol-relative `//host` both fetch through spellings a
 * `https?:` test does not see.
 *
 * The exemption is written as TWO clauses because one is not enough, and the
 * cross-review demonstrated exactly why: `<img src="data:…"
 * srcset="https://…">` satisfies "the src is a data URI" while still fetching
 * through the other attribute. An exemption that inspects one attribute of a
 * tag that fetches through several is not an exemption, it is a hole. So the
 * second clause refuses ANY `<img>` carrying `srcset`, however innocent its
 * `src` looks.
 */
const EXTERNAL_REF =
  /<script[^>]+\bsrc\s*=|<link[^>]+\bhref\s*=|<(?:object|embed|iframe|video|audio|source|track|image)\b|<img\b(?![^>]*\bsrc\s*=\s*["']data:)|<img\b[^>]*\bsrcset\s*=|<meta[^>]+\bhttp-equiv\s*=\s*["']?refresh/i;

/**
 * An off-origin fetch from CSS — checked only where CSS is EXECUTED.
 *
 * The scoping is the entire point, and it is why `@import` moved out of
 * `EXTERNAL_REF` and into here. `esc()` neutralises markup from a gathered
 * snippet — `<object` becomes `&lt;object` — but it does not escape
 * parentheses, colons or `@`, so a target whose own config contains the text
 * `@import url(https://cdn.example.com/x.css)` (a stylesheet is a perfectly
 * ordinary thing for a repository to contain) tripped a document-wide scan and
 * the whole report refused to render. Rejecting a valid report because the
 * repository it measured mentions a URL is exactly the check that reads
 * something other than what it claims to read — the failure this tool is named
 * after, committed by the tool itself.
 *
 * In body text these strings are inert. They fetch in exactly two places: a
 * `<style>` block and a `style="…"` attribute. Both are enumerated below, and
 * both are ours — the only `style` attribute the template emits is the meter's
 * `width:{{WIDTH}}%`, whose slot is a number.
 *
 * `image-set()` is named alongside `url()` because it is a second CSS function
 * that fetches, and a guard that knows only about the first is a guard with a
 * documented hole. Protocol-relative `//host/…` counts: it inherits the page's
 * scheme and fetches just as well as an absolute URL.
 */
const STYLE_BLOCK = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
const STYLE_ATTR = /\bstyle\s*=\s*"([^"]*)"|\bstyle\s*=\s*'([^']*)'/gi;
const CSS_EXTERNAL_REF =
  /@import\s+(?:url\(|["'])|(?:url|(?:-webkit-)?image-set)\(\s*["']?\s*(?:https?:|\/\/)/i;

/**
 * The same question asked of an SVG fragment we did not write.
 *
 * It reuses `CSS_EXTERNAL_REF` rather than carrying its own copy of the CSS
 * rules: the two had drifted, and the drift was reachable — an SVG carrying
 * `style=background-image:image-set(https://…)` passed this while the same
 * declaration in a `<style>` block was refused, because only one of the two
 * patterns had learned about `image-set`. One definition of "this CSS fetches"
 * means a hole closed in one place is closed in both.
 *
 * Protocol-relative `//host/…` is included for the same reason it is there:
 * it inherits the page scheme and fetches exactly like an absolute URL.
 */
const SVG_EXTERNAL_REF = new RegExp(
  [
    '<script\\b',
    '<image\\b',
    'xlink:href\\s*=\\s*["\'](?:https?:|//)',
    '\\bhref\\s*=\\s*["\'](?:https?:|//)',
    CSS_EXTERNAL_REF.source,
  ].join('|'),
  'i',
);

// ---------------------------------------------------------------------------
// Template engine — substitution only, on purpose.
// ---------------------------------------------------------------------------

type Slots = Record<string, string>;

export type Template = Record<string, string>;

const BLOCK =
  /<!--@block\s+([a-zA-Z0-9_-]+)\s*-->\n?([\s\S]*?)<!--@endblock\s*-->/g;

/**
 * An authoring note: present in the template file, stripped from the output.
 *
 * There is exactly one reason this exists, and it is not tidiness. `make
 * design-audit` reads the HTML under `templates/` and also reads whatever the
 * renderer publishes, and one of its rules (`data-specimen-defect`) means
 * "this markup is a SPECIMEN of the defect state, do not fail on it". The
 * defect specimen has to live in the template — that is what makes the rule
 * teachable — but a real argument-less verdict in a real report is not a
 * specimen, and emitting the hatch onto it would make the gate wave through
 * precisely the failure the gate exists to catch. A note keeps the hatch on
 * the file the auditor is auditing and off the artifact it is not.
 *
 * `<!-- KEEL:CURVE -->` is deliberately NOT of this form: it is a contract
 * with W1·G's curve unit and must survive into the output.
 */
const NOTE = /[ \t]*<!--@note\b[\s\S]*?-->[ \t]*\n?/g;

export function parseTemplate(text: string): Template {
  const blocks: Template = {};
  for (const m of text.matchAll(BLOCK))
    blocks[m[1] as string] = (m[2] as string).replace(NOTE, '');
  return blocks;
}

export function esc(value: unknown): string {
  return String(value)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Fill a block. `{{{RAW}}}` is inserted verbatim (already-rendered markup);
 * `{{SLOT}}` is HTML-escaped. An unfilled slot throws — a `{{NAME}}` shipped
 * into the artifact is a silent defect, and this renderer's whole subject is
 * silent defects.
 *
 * The completeness check runs over the TEMPLATE, before substitution, never
 * over the result. A gathered snippet legitimately contains `${{ ... }}` (every
 * GitHub Actions expression does, and the fixture carries one), so scanning the
 * filled output for a leftover slot would fail on the target's text rather than
 * on our own defect — a check reading something other than what it claims to
 * read, which is the thing this tool exists to name.
 */
function fill(block: string, slots: Slots): string {
  for (const [, raw, esc_] of block.matchAll(/\{\{\{(\w+)\}\}\}|\{\{(\w+)\}\}/g)) {
    const key = raw ?? esc_;
    if (key !== undefined && !(key in slots)) {
      throw new Error(`unfilled template slot {{${key}}}`);
    }
  }
  // ONE pass. Two chained replaces would rescan the text the first pass
  // inserted, so a gathered snippet containing `{{something}}` would be read as
  // a slot in the template that carried it.
  return block.replace(
    /\{\{\{(\w+)\}\}\}|\{\{(\w+)\}\}/g,
    (_, raw: string | undefined, escaped: string) =>
      raw !== undefined ? (slots[raw] as string) : esc(slots[escaped] as string),
  );
}

// ---------------------------------------------------------------------------
// Formatting
// ---------------------------------------------------------------------------

const num = (n: number): string => n.toLocaleString('en-US');

function duration(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return `${ms} ms`;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  if (ms < 60_000) return `${(ms / 1000).toFixed(1)} s`;
  const m = Math.floor(ms / 60_000);
  const s = Math.round((ms % 60_000) / 1000);
  return `${m}m ${String(s).padStart(2, '0')}s`;
}

function pct(part: number, whole: number): number {
  return whole === 0 ? 0 : (part / whole) * 100;
}

const plural = (n: number, one: string, many: string): string =>
  `${num(n)} ${n === 1 ? one : many}`;

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

export interface RenderOptions {
  /** Inlined verbatim at the `<!-- KEEL:CURVE -->` marker when present. */
  curveSvg?: string;
  /** Shown when a curve was found but refused for referencing something off-origin. */
  curveRejectedPath?: string;
  /**
   * The gatherer's coverage record, read from a sibling of `report.json`.
   *
   * A SIDE-CHANNEL, deliberately: `Report` is the frozen contract, this unit
   * does not get to add a field to it, and a renderer that invented one would
   * have every consumer reading a shape the schema does not describe. So the
   * record travels beside the report the way `reports/curve.svg` already does.
   * The cost is real and is stated rather than hidden: a report handed on
   * without its sibling renders with no blindness card at all, and the reader
   * cannot tell that from a run that had nothing to report. Only a schema field
   * closes that, and only the orchestrator can open the schema.
   */
  coverage?: GatherCoverage;
  /** Shown when a coverage sibling was found but is not a record we can read. */
  coverageRejectedPath?: string;
  /** Overrides the on-disk template + stylesheets (tests). */
  template?: Template;
  styles?: string;
}

function isGroundingClass(value: string): value is GroundingClass {
  return (CLASS_ORDER as string[]).includes(value);
}

function smellsOf(v: Verdict): boolean {
  return v.class === 'anchored' && v.confidence < SMELL_THRESHOLD;
}

/**
 * The ε-audit tally — Keel's counter-metric, counted rather than judged.
 *
 * Every field below is a count over verdicts that already carry their own
 * `audit.agreed`. This function decides nothing: it does not re-open a
 * comparison, does not weigh one against another, and does not have an opinion
 * about whether a verdict "really" agreed. That distinction is the line
 * between arithmetic (allowed here) and judgment (not).
 *
 * A block only counts once it DESCRIBES a comparison. `agreed: true` with no
 * `agentClass` names no re-decided class, so no comparison happened — counting
 * it as agreement would let a verdict assert its own audit passed, which is a
 * status field the actor sets, on the one number that exists to catch that.
 * Counting it as a *disagreement* is equally false, and worse than it looks: the
 * summary then claims a disagreement no verdict can be shown for, because the
 * per-verdict branch has no class to render.
 *
 * So malformed blocks are excluded from `compared` and reported as `malformed`.
 * A comparison that cannot be read is not evidence — the same fail-closed move
 * `classify.ts` makes when it drops a probe verdict claiming `unknown` and hands
 * the node back to the agent, rather than letting an unreadable answer become a
 * cheap one. Zero WELL-FORMED comparisons is therefore "not run", whatever
 * wreckage arrived alongside.
 */
export interface AuditTally {
  /** verdicts carrying a WELL-FORMED `audit` block. The agreement denominator. */
  compared: number;
  agreed: number;
  disagreed: number;
  /** blocks present but unreadable. Excluded from `compared`; disclosed, never silent. */
  malformed: number;
  /** the population the ε-audit samples from. */
  probeDecided: number;
  /** how many of that population were actually audited — coverage. */
  probeAudited: number;
  /** audited verdicts outside that population. Counted in agreement, stated separately. */
  auditedNonProbe: number;
  /**
   * Agreement restricted to probe-decided verdicts — the number SKILL.md §4
   * actually names.
   *
   * `compared` pools every well-formed comparison, and an audit may legally sit
   * on an agent-decided verdict, so the pooled figure is not the probe library's
   * agreement whenever the two populations differ. Both are carried so the card
   * can print both rather than letting one borrow the other's meaning — the same
   * partition `corpus.ts` already makes between agent, probe, mixed and pooled
   * repeatability, and for the same reason.
   */
  probeAgreed: number;
}

/**
 * Does this verdict carry an audit block that actually states a comparison?
 *
 * Four conditions, none of them a formality:
 *
 *   `agentClass` — the class the agent re-decided. Without it there is nothing
 *   to compare against.
 *
 *   `agreed` — a real boolean. `"yes"`, `1` and `null` are not verdicts about
 *   the world, they are a producer's typo.
 *
 *   `at` — a non-empty string. The frozen schema requires it, and without it
 *   the per-verdict row printed the literal text `undefined` as the moment the
 *   comparison happened. A record that cannot say when it was made is not a
 *   record of a comparison, and a `1 / 1 · rate 1.00` sitting above an
 *   `undefined` timestamp is the cheap green this card exists to catch.
 *
 *   INTERNAL CONSISTENCY — `agreed` must equal `agentClass === v.class`. This
 *   is the condition the artifact already claims in prose: the disagreement row
 *   says the two classes differ and that one of them is wrong. A block saying
 *   `agreed: false` while naming the class the verdict already carries makes
 *   that sentence false, and a block saying `agreed: true` while naming a
 *   different class hides a real disagreement inside the agreement count —
 *   which is the one direction this whole card exists to prevent.
 *
 * This last check is arithmetic on two fields that arrived together, not a
 * judgment about the world: it does not decide which of the two is right, and
 * it never promotes or demotes a node. It says the record contradicts itself,
 * and a self-contradictory record states no comparison. Like every other
 * unreadable shape it is excluded from the denominator and named — because the
 * honest answer to "these two fields disagree" is to report that, not to pick
 * a winner.
 */
export function auditIsWellFormed(v: Verdict): boolean {
  const a = v.audit;
  if (a === null || typeof a !== 'object') return false;
  if (typeof a.agentClass !== 'string' || !isGroundingClass(a.agentClass)) return false;
  if (typeof a.agreed !== 'boolean') return false;
  if (typeof a.at !== 'string' || a.at.trim() === '') return false;
  return a.agreed === (a.agentClass === v.class);
}

export function auditTally(verdicts: Verdict[]): AuditTally {
  const present = verdicts.filter((v) => 'audit' in v && v.audit !== undefined);
  const wellFormed = present.filter(auditIsWellFormed);
  const agreed = wellFormed.filter((v) => v.audit?.agreed === true).length;
  const probeAudited = wellFormed.filter((v) => v.decidedBy === 'probe').length;
  return {
    compared: wellFormed.length,
    agreed,
    disagreed: wellFormed.length - agreed,
    malformed: present.length - wellFormed.length,
    probeDecided: verdicts.filter((v) => v.decidedBy === 'probe').length,
    probeAudited,
    auditedNonProbe: wellFormed.length - probeAudited,
    probeAgreed: wellFormed.filter(
      (v) => v.decidedBy === 'probe' && v.audit?.agreed === true,
    ).length,
  };
}

/**
 * How many unread paths are printed before the list is elided.
 *
 * A Bazel monorepo has a `BUILD` file per package and would otherwise push the
 * ratio off the screen with a thousand rows. The elision is stated in the same
 * breath — an undisclosed truncation on the one card whose subject is undisclosed
 * absence would be a joke at this tool's expense.
 */
const MAX_UNREAD_ROWS = 12;

/**
 * The blindness card — what the gatherer recognised and did not read.
 *
 * It renders BESIDE the ratio, in the same block, and not in a footer. That is
 * a claim about meaning, not layout: "we could not read your Jenkinsfile"
 * changes how the number above should be read, and a reader who forms an
 * impression of the ratio and then meets the caveat two screens later has
 * already formed the wrong impression. The ε-audit card is placed by the same
 * argument.
 *
 * The empty state prints too, and this is the important half. A card that
 * appears only when something is missing leaves absence unreadable — "no card"
 * would mean both "nothing was left unread" and "nobody checked", which is
 * precisely the ambiguity between an empty repo and a blind gatherer that this
 * whole feature exists to break. What is NOT printed is a card when there is no
 * coverage record at all: with no record we know nothing, and rendering
 * "nothing unread" from silence would be defaulting to clean — the same fail-open
 * move as defaulting a node to `anchored`.
 *
 * Markup is assembled here rather than in `templates/report.html` because that
 * file is not this unit's to edit; every class used is an existing design-system
 * class and no new CSS is introduced. A template block is proposed in the PR body.
 */
function renderBlindness(cov: GatherCoverage): string {
  const parts: string[] = [];
  const blind = cov.blind ?? [];
  const total = cov.unread.length + cov.silent.length + blind.length;

  // The counts are labelled separately in the heading rather than summed into
  // one figure. They are different facts — one surface was never opened, one
  // was opened and gave nothing back, one could not be opened at all — and a
  // single total invites the reader to check it against lists that do not add
  // up to it.
  const heading =
    total === 0
      ? 'none'
      : [
          cov.unread.length > 0 ? `${num(cov.unread.length)} unread` : '',
          cov.silent.length > 0 ? `${num(cov.silent.length)} read-but-silent` : '',
          blind.length > 0 ? `${num(blind.length)} unreadable` : '',
        ]
          .filter(Boolean)
          .join(', ');
  parts.push(`<p class="k-eyebrow">Unread surfaces — ${heading}</p>`);

  if (total === 0) {
    // Reachable only when the walk itself came back whole. `blind` is inside
    // `total` precisely so this sentence cannot print over a directory the
    // gatherer could not open: "it also read" is a claim about the tree, and a
    // walk that failed has no standing to make it.
    parts.push(
      '<p>Every verification surface this gatherer recognises in the target, it also read. ' +
        'The coverage above therefore describes the surface that exists, not the part of it ' +
        'that happened to be parseable.</p>',
      '<p class="k-meta">Recognition is by filename. A CI provider this gatherer has never ' +
        'heard of is still invisible, and no run can say otherwise — this line means ' +
        '"nothing known was missed", not "nothing was missed".</p>',
    );
  } else {
    if (cov.unread.length > 0) {
      const shown = cov.unread.slice(0, MAX_UNREAD_ROWS);
      const rows = shown
        .map(
          (u) =>
            `      <tr><td class="k-mono">${esc(u.path)}${u.kind === 'dir' ? '/' : ''}</td><td>${esc(u.tool)}</td></tr>`,
        )
        .join('\n');
      parts.push(
        `<p>${plural(cov.unread.length, 'surface was', 'surfaces were')} recognised by name and ` +
          'never opened — this gatherer has no parser for them. They contributed no node, no ' +
          'verdict and no denominator, so the ratio beside this card describes what could be ' +
          'read, not this target. A repo whose real verification lives in one of these scores ' +
          'like a repo with none.</p>',
        '<table class="k-table">',
        '    <thead><tr><th>surface</th><th>tool</th></tr></thead>',
        `    <tbody>\n${rows}\n    </tbody>`,
        '</table>',
      );
      if (cov.unread.length > shown.length) {
        parts.push(
          `<p class="k-meta">${num(cov.unread.length - shown.length)} further unread ` +
            `path(s) are not listed here. The full list is in the coverage record beside ` +
            `this report.</p>`,
        );
      }
    }

    if (cov.silent.length > 0) {
      const rows = cov.silent
        .slice(0, MAX_UNREAD_ROWS)
        .map(
          (s) =>
            `      <tr><td class="k-mono">${esc(s.path)}</td><td class="k-mono">${esc(s.parser)}</td></tr>`,
        )
        .join('\n');
      parts.push(
        `<p class="k-meta">${plural(cov.silent.length, 'CI definition was', 'CI definitions were')} ` +
          'opened by a parser here and produced nothing. The file was read; the reader came ' +
          'back empty. That is a gap in this gatherer, not a fact about the target.</p>',
        '<table class="k-table">',
        '    <thead><tr><th>surface</th><th>reader</th></tr></thead>',
        `    <tbody>\n${rows}\n    </tbody>`,
        '</table>',
      );
    }

    if (blind.length > 0) {
      const rows = blind
        .slice(0, MAX_UNREAD_ROWS)
        .map(
          (b) =>
            `      <tr><td class="k-mono">${esc(b.path)}</td><td class="k-mono">${esc(b.by)}</td><td>${esc(b.reason)}</td></tr>`,
        )
        .join('\n');
      parts.push(
        `<p>${plural(blind.length, 'surface was', 'surfaces were')} attempted and could ` +
          'not be read — the walk could not enumerate a directory, or stopped at its depth ' +
          'limit, or a parser threw partway through a file. Whatever was inside is absent ' +
          'from every number on this page, and this run cannot say what it was. A read ' +
          'failure is not an empty tree, and it is the one confusion this card exists to ' +
          'prevent.</p>',
        '<table class="k-table">',
        '    <thead><tr><th>surface</th><th>attempted by</th><th>why it stopped</th></tr></thead>',
        `    <tbody>\n${rows}\n    </tbody>`,
        '</table>',
      );
      if (blind.length > MAX_UNREAD_ROWS) {
        parts.push(
          `<p class="k-meta">${num(blind.length - MAX_UNREAD_ROWS)} further unreadable ` +
            'path(s) are not listed here. The full list is in the coverage record beside ' +
            'this report.</p>',
        );
      }
    }
  }

  // The record names the tree it walked. Printed rather than compared against
  // `report.target`: a corpus run gathers a clone under /tmp and files the
  // report under the repo's name, so the two legitimately differ and a mismatch
  // alarm would fire on every honest run. Showing both lets a reader pair them.
  parts.push(
    `<p class="k-meta">From a gather of <span class="k-mono">${esc(cov.target)}</span> ` +
      `(${plural(cov.nodesGathered, 'edge', 'edges')} gathered).</p>`,
  );

  return `<div class="k-card">\n${parts.join('\n')}\n</div>`;
}

/** Shown in place of the card when a sibling was found but could not be read. */
function renderBlindnessRejected(path: string): string {
  return (
    '<div class="k-card">\n' +
    '<p class="k-eyebrow">Unread surfaces — unavailable</p>\n' +
    `<p>A coverage record was found at <span class="k-mono">${esc(path)}</span> and is not ` +
    'a <span class="k-mono">keel.gather-coverage.v1</span> record, so nothing is claimed from it. ' +
    'This report cannot say which surfaces the gatherer failed to read.</p>\n' +
    '<p class="k-meta">Regenerate it with <span class="k-mono">gather.ts --coverage</span> ' +
    'against the same tree, or read the ratio as covering only the surfaces named under ' +
    'coverage.</p>\n' +
    '</div>'
  );
}

export function render(report: Report, opts: RenderOptions = {}): string {
  const t = opts.template ?? loadTemplate();
  const styles = opts.styles ?? loadStyles();

  const nodes: Node[] = report.nodes ?? [];
  const verdicts: Verdict[] = report.verdicts ?? [];
  const byNode = new Map(verdicts.map((v) => [v.nodeId, v]));
  const nodeById = new Map(nodes.map((n) => [n.id, n]));

  // Recomputed from the verdicts rather than read off `report.grounding`. The
  // stated field is a claim by the producer; the recomputation is a signal the
  // producer cannot write to, which is the whole thesis applied to ourselves.
  const g = groundingRatio(verdicts);
  const denominator = g.anchored + g.selfReferential + g.unknown;

  const body: string[] = [];
  const disclosures: string[] = [];

  body.push(
    fill(t.header as string, {
      TARGET: report.target,
      REVISION: report.revision,
      GENERATED: report.generatedAt,
    }),
  );

  // ── The headline, and the two states that are not one ────────────────────
  const coverage = coverageByKind(nodes);
  const coverageBlock = fill(t.coverage as string, {
    ROWS: Object.entries(coverage)
      .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]))
      .map(([kind, n]) =>
        fill(t['coverage-row'] as string, { KIND: kind, N: num(n) }),
      )
      .join(''),
    JUDGED: num(nodes.length),
  });

  // Empty when no coverage record travelled with the report — see RenderOptions.
  const blindness = opts.coverage
    ? renderBlindness(opts.coverage)
    : opts.coverageRejectedPath
      ? renderBlindnessRejected(opts.coverageRejectedPath)
      : '';

  if (nodes.length === 0 && verdicts.length === 0) {
    // The state where blindness matters most: "nothing gathered" and "nothing
    // readable" print the same sentence otherwise, and they are opposite facts.
    body.push(t['nothing-gathered'] as string);
    if (blindness) body.push(`<div class="kr-section">${blindness}</div>`);
  } else if (denominator === 0) {
    body.push(
      `<div class="kr-split">${fill(t['no-denominator'] as string, {
        JUDGED: num(verdicts.length),
      })}${coverageBlock}${blindness}</div>`,
    );
  } else {
    const meter = DENOMINATOR_CLASSES.map((c) =>
      fill(t['meter-seg'] as string, {
        CLASS: c,
        WIDTH: pct(countOf(g, c), denominator).toFixed(4),
      }),
    ).join('');

    const counts =
      DENOMINATOR_CLASSES.map((c) =>
        fill(t.count as string, { CLASS: c, N: num(countOf(g, c)) }),
      ).join('') +
      fill(t['count-excluded'] as string, { N: num(g.notACheck) });

    const ratioBlock = fill(t.ratio as string, {
      VALUE: g.ratio.toFixed(2),
      ANCHORED: num(g.anchored),
      DENOMINATOR: num(denominator),
      METER: meter,
      COUNTS: counts,
    });
    body.push(
      `<div class="kr-split">${ratioBlock}${coverageBlock}${blindness}</div>`,
    );
  }

  // ── Keel's own counter-metric, beside Keel's own number ──────────────────
  // Unconditional. The zero state is the whole reason this is not rendered
  // "when there is something to show": a run that audited nothing has to say
  // so, in the same place a run that audited something says what it found.
  body.push(renderAudit(t, auditTally(verdicts)));

  // ── Disclosures: every place a number is narrower than it looks ──────────
  const econ = report.economics;
  if (econ && econ.nodesSampled !== econ.nodesTotal) {
    const skipped = econ.nodesTotal - econ.nodesSampled;
    disclosures.push(
      `This run judged <span class="k-mono">${num(econ.nodesSampled)}</span> of ` +
        `<span class="k-mono">${num(econ.nodesTotal)}</span> gathered edges. ` +
        `Every number on this page describes that sample, not the whole surface — ` +
        `${plural(skipped, 'gathered edge is', 'gathered edges are')} absent from all of it. ` +
        `A cap is disclosed rather than smoothed: an undisclosed sample is how a ratio gets shopped.`,
    );
  }
  if (econ && nodes.length !== econ.nodesSampled) {
    disclosures.push(
      `The report carries <span class="k-mono">${num(nodes.length)}</span> node(s) but ` +
        `economics reports <span class="k-mono">${num(econ.nodesSampled)}</span> sampled. ` +
        `The graph and coverage below describe the nodes actually present.`,
    );
  }
  const unjudged = nodes.filter((n) => !byNode.has(n.id));
  if (unjudged.length > 0) {
    disclosures.push(
      `${plural(unjudged.length, 'node carries', 'nodes carry')} no verdict. ` +
        `They are drawn unfilled in the graph and excluded from every count — ` +
        `absence of a verdict is not <span class="k-mono">anchored</span>, and it is not ` +
        `<span class="k-mono">unknown</span> either, because nobody looked.`,
    );
  }
  const orphans = verdicts.filter((v) => !nodeById.has(v.nodeId));
  if (orphans.length > 0) {
    disclosures.push(
      `${plural(orphans.length, 'verdict names a node', 'verdicts name nodes')} ` +
        `that is not in this report. The verdict is still listed below, with its ` +
        `node id in place of a source.`,
    );
  }
  const stated = report.grounding;
  if (
    stated &&
    (stated.anchored !== g.anchored ||
      stated.selfReferential !== g.selfReferential ||
      stated.unknown !== g.unknown ||
      stated.notACheck !== g.notACheck)
  ) {
    disclosures.push(
      `The ratio shown is recomputed from the verdicts in this report and ` +
        `disagrees with the <span class="k-mono">grounding</span> block the report carried ` +
        `(<span class="k-mono">${num(stated.anchored)}/${num(stated.selfReferential)}/${num(stated.unknown)}/${num(stated.notACheck)}</span> ` +
        `stated versus <span class="k-mono">${num(g.anchored)}/${num(g.selfReferential)}/${num(g.unknown)}/${num(g.notACheck)}</span> ` +
        `counted). The counted figure is shown, because a stated total is a claim by ` +
        `the thing being measured.`,
    );
  }
  for (const text of disclosures) {
    body.push(fill(t.disclosure as string, { TEXT: text }));
  }

  body.push(t.scope as string);

  // ── Node graph ───────────────────────────────────────────────────────────
  if (nodes.length > 0) {
    const marks = nodes
      .map((n) => {
        const v = byNode.get(n.id);
        if (!v) {
          return fill(t['mark-unjudged'] as string, {
            TITLE: `${n.name} — ${n.source} — no verdict recorded`,
          });
        }
        return fill(t.mark as string, {
          CLASS: v.class,
          SMELL: smellsOf(v) ? ' data-smell' : '',
          TITLE: `${n.name} — ${n.source} — ${v.class} (confidence ${v.confidence})`,
        });
      })
      .join('');

    // The legend counts the marks ACTUALLY DRAWN, not the verdict totals. One
    // mark is drawn per node; a verdict naming a node absent from this report
    // has no mark, so counting it in the legend would leave a reader who counts
    // squares unable to reconcile them against the numbers underneath. In a
    // tool whose entire claim is that counts must reconcile, a legend that
    // over-counts its own picture is not a cosmetic defect. The orphans are
    // not dropped — they get their own item, marked as not drawn.
    const drawnVerdicts = nodes
      .map((n) => byNode.get(n.id))
      .filter((v): v is Verdict => v !== undefined);
    const drawn = new Map<string, number>();
    for (const v of drawnVerdicts) {
      drawn.set(v.class, (drawn.get(v.class) ?? 0) + 1);
    }
    const unrecognizedDrawn = [...drawn.entries()]
      .filter(([c]) => !isGroundingClass(c))
      .reduce((sum, [, n]) => sum + n, 0);

    const aside = (TEXT: string) =>
      fill(t['legend-item-aside'] as string, { TEXT });

    const legend =
      CLASS_ORDER.filter((c) => (drawn.get(c) ?? 0) > 0)
        .map((c) =>
          fill(t['legend-item'] as string, {
            CLASS: c,
            N: num(drawn.get(c) as number),
          }),
        )
        .join('') +
      (unjudged.length > 0
        ? fill(t['legend-item-unjudged'] as string, { N: num(unjudged.length) })
        : '') +
      (unrecognizedDrawn > 0
        ? aside(
            `${plural(unrecognizedDrawn, 'mark carries', 'marks carry')} a class the frozen schema does not define — drawn uncoloured, listed below`,
          )
        : '') +
      (orphans.length > 0
        ? aside(
            `not drawn — ${plural(orphans.length, 'verdict names a node', 'verdicts name nodes')} absent from this report`,
          )
        : '');

    const smellCount = drawnVerdicts.filter(smellsOf).length;
    body.push(
      fill(t.graph as string, {
        COUNT: num(nodes.length),
        MARKS: marks,
        LEGEND: legend,
        SMELL_NOTE:
          smellCount > 0
            ? `${plural(smellCount, 'mark is', 'marks are')} ringed in the unknown hue: an anchored verdict asserted below confidence ${SMELL_THRESHOLD}. The ring says the claim is closer to unknown than its colour suggests. Hover a mark for its node.`
            : `No mark is ringed: no drawn verdict is anchored below confidence ${SMELL_THRESHOLD}. Hover a mark for its node.`,
      }),
    );
  }

  // ── Verdicts, grouped by class, argument first ───────────────────────────
  const order = new Map(nodes.map((n, i) => [n.id, i]));
  const sorted = [...verdicts].sort(
    (a, b) =>
      (order.get(a.nodeId) ?? Number.MAX_SAFE_INTEGER) -
      (order.get(b.nodeId) ?? Number.MAX_SAFE_INTEGER),
  );

  for (const c of CLASS_ORDER) {
    const rows = sorted.filter((v) => v.class === c);
    if (rows.length === 0) continue;
    body.push(
      fill(t['verdict-section'] as string, {
        LABEL: c,
        N: num(rows.length),
        NOTE: CLASS_NOTE[c],
        VERDICTS: rows.map((v) => renderVerdict(t, v, nodeById)).join(''),
      }),
    );
  }

  const unrecognized = sorted.filter((v) => !isGroundingClass(v.class));
  if (unrecognized.length > 0) {
    body.push(
      fill(t['verdict-section'] as string, {
        LABEL: 'not a GroundingClass',
        N: num(unrecognized.length),
        NOTE: 'These verdicts carry a class the frozen schema does not define. They render unstyled on purpose: an unrecognised class must look wrong rather than default to something plausible.',
        VERDICTS: unrecognized
          .map((v) => renderVerdict(t, v, nodeById))
          .join(''),
      }),
    );
  }

  // ── Curve insertion point ────────────────────────────────────────────────
  let curveInner = '';
  if (opts.curveSvg) {
    // The curve is the ONE fragment spliced in raw, and it is the only content
    // in the document that `esc()` never touched. So it is asked the fragment
    // question HERE, at the boundary it enters, rather than left to a scan of
    // the finished document.
    //
    // That placement is the fix for a real pair of defects the cross-review
    // found, which pulled in opposite directions and together showed the
    // document-wide scan was the wrong instrument: an unquoted
    // `style=fill:url(https://…)` slipped past an attribute matcher that
    // expects quotes, while `<text>style="background:url(https://…)"</text>` —
    // inert prose inside an SVG label — was falsely refused. A regex reading a
    // finished document cannot tell an attribute from text shaped like one.
    // Reading the fragment as a fragment can, and `loadCurve` already applied
    // exactly this check on the CLI path — so this closes the gap for every
    // caller that passes `curveSvg` directly, rather than only the one that
    // went through the loader.
    const offending = opts.curveSvg.match(SVG_EXTERNAL_REF);
    if (offending) {
      throw new Error(
        `refusing to write: the supplied curve references something off-origin (${offending[0]})`,
      );
    }
    curveInner = fill(t.curve as string, { SVG: opts.curveSvg });
  } else if (opts.curveRejectedPath) {
    curveInner = fill(t['curve-rejected'] as string, {
      PATH: opts.curveRejectedPath,
    });
  }
  body.push(fill(t['curve-slot'] as string, { CURVE: curveInner }));

  // ── Economics ────────────────────────────────────────────────────────────
  if (econ) body.push(renderEconomics(t, econ));

  const html = fill(t.document as string, {
    TITLE: `Keel — grounding report — ${report.target}`,
    STYLES: `${styles}\n\n/* ── renderer-local layout (kr-*), tokens only ── */\n${t['layout-css'] as string}`,
    BODY: body.join('\n'),
  });

  // Executed, not asserted: the invariant is checked against the bytes about to
  // be written, so a regression fails the run instead of shipping quietly.
  const offending = html.match(EXTERNAL_REF);
  if (offending) {
    throw new Error(
      `refusing to write: output contains an off-origin document reference (${offending[0]})`,
    );
  }
  // The CSS question, asked in both places CSS executes. See CSS_EXTERNAL_REF.
  for (const [where, pattern] of [
    ['<style> block', STYLE_BLOCK],
    ['style="" attribute', STYLE_ATTR],
  ] as const) {
    for (const m of html.matchAll(pattern)) {
      const css = m[1] ?? m[2] ?? '';
      const fetched = css.match(CSS_EXTERNAL_REF);
      if (fetched) {
        throw new Error(
          `refusing to write: a ${where} fetches something off-origin (${fetched[0]})`,
        );
      }
    }
  }
  return html;
}

function countOf(
  g: ReturnType<typeof groundingRatio>,
  c: GroundingClass,
): number {
  switch (c) {
    case 'anchored':
      return g.anchored;
    case 'self_referential':
      return g.selfReferential;
    case 'unknown':
      return g.unknown;
    case 'not_a_check':
      return g.notACheck;
  }
}

function renderVerdict(
  t: Template,
  v: Verdict,
  nodeById: Map<string, Node>,
): string {
  const node = nodeById.get(v.nodeId);
  const wb = v.writeBoundary;
  const actor =
    wb?.actorCanWrite === true
      ? 'yes'
      : wb?.actorCanWrite === false
        ? 'no'
        : 'not established';

  const evidence = (v.evidence ?? []).length
    ? (v.evidence as string[])
        .map((e) => fill(t['evidence-item'] as string, { TEXT: e }))
        .join('')
    : (t['evidence-empty'] as string);

  // A verdict that arrived without its causal path is rendered through the
  // defect variant, which OMITS `.k-argument` entirely. Emitting an empty
  // paragraph would satisfy `keel.css`'s `:not(:has(.k-argument))` selector and
  // silence the defect banner — a renderer quietly papering over a missing
  // argument is the unaccountable green check, produced by the tool that exists
  // to name it. No placeholder text either: inventing prose here would be worse
  // than a blank, because it would read as an argument someone made.
  const argument = wb?.argument?.trim() ?? '';
  const block = argument ? (t.verdict as string) : (t['verdict-defect'] as string);

  return fill(block, {
    NAME: node ? node.name : v.nodeId,
    CLASS: v.class,
    SMELL: smellsOf(v) ? ' data-smell' : '',
    SOURCE: node ? node.source : `${v.nodeId} (node not in report)`,
    KIND: node ? node.kind : 'unknown kind',
    ARGUMENT: argument,
    PRODUCER: wb?.producer ?? 'not recorded',
    ACTOR_CAN_WRITE: actor,
    EVIDENCE: evidence,
    DECIDED_BY: v.decidedBy,
    PROBE: v.probeId
      ? fill(t['probe-id'] as string, { ID: v.probeId })
      : '',
    CONFIDENCE: String(v.confidence),
    SMELL_NOTE: smellsOf(v)
      ? fill(t['smell-note'] as string, { THRESHOLD: String(SMELL_THRESHOLD) })
      : '',
    // The re-decided class is printed as it arrived. A disagreement gets the
    // loud variant because it is the most informative thing on the page: it is
    // the one outcome that says a probe is mis-classifying, and the whole
    // reason stage 4 exists. `agreed === true` is the only shape that takes
    // the quiet variant — see `auditTally`.
    AUDIT: !('audit' in v) || v.audit === undefined
      ? ''
      : !auditIsWellFormed(v)
        ? (t['verdict-audit-malformed'] as string)
        : v.audit?.agreed === true
          ? fill(t['verdict-audit'] as string, {
              AGENT_CLASS: v.audit.agentClass,
              AT: v.audit.at,
            })
          : fill(t['verdict-audit-disagreed'] as string, {
              AGENT_CLASS: v.audit?.agentClass ?? '',
              CLASS: v.class,
              AT: v.audit?.at ?? '',
            }),
  });
}

/**
 * The ε-audit card. Every branch here is a lookup into `t`; the prose lives in
 * `templates/report.html` and the numbers arrive already counted.
 */
function renderAudit(t: Template, a: AuditTally): string {
  // Zero comparisons is a STATE, not a rate — the same refusal `nothing
  // gathered` makes above, by the same mechanism (a different block, not a
  // different number). `1.00` over an empty audit is the most flattering
  // figure this file could print and the least earned one, and an unaudited
  // library is an absence of evidence: the tool exists to stop that reading as
  // evidence.
  // Malformed blocks are disclosed wherever we land, because "an audit arrived
  // and could not be read" is a fact about the run, and swallowing it would make
  // non-coverage invisible in exactly the way this card exists to prevent.
  const malformed =
    a.malformed > 0
      ? fill(t['audit-malformed'] as string, { N: num(a.malformed) })
      : '';

  if (a.compared === 0) {
    return fill(t['audit-none'] as string, {
      PROBE_DECIDED: num(a.probeDecided),
      MALFORMED: malformed,
    });
  }

  // A coverage percentage over an empty probe population is the same
  // fabrication one scope down, so it gets the same treatment.
  const coverage =
    a.probeDecided === 0
      ? (t['audit-coverage-none'] as string)
      : fill(t['audit-coverage'] as string, {
          AUDITED: num(a.probeAudited),
          PROBE_DECIDED: num(a.probeDecided),
          PCT: pct(a.probeAudited, a.probeDecided).toFixed(0),
        });

  return fill(t.audit as string, {
    AGREED: num(a.agreed),
    COMPARED: num(a.compared),
    RATE: (a.agreed / a.compared).toFixed(2),
    DISAGREED: num(a.disagreed),
    DISAGREEMENT:
      a.disagreed > 0
        ? fill(t['audit-disagreement'] as string, { N: num(a.disagreed) })
        : '',
    COVERAGE: coverage,
    NONPROBE:
      // Only when the populations differ. Where every comparison is
      // probe-decided the headline already IS the probe library's agreement,
      // and restating it would read as a second, independent number.
      a.auditedNonProbe === 0
        ? ''
        : a.probeAudited === 0
          ? fill(t['audit-nonprobe-only'] as string, { N: num(a.auditedNonProbe) })
          : fill(t['audit-nonprobe'] as string, {
              N: num(a.auditedNonProbe),
              PROBE_AGREED: num(a.probeAgreed),
              PROBE_COMPARED: num(a.probeAudited),
              PROBE_RATE: ` (rate ${(a.probeAgreed / a.probeAudited).toFixed(2)})`,
            }),
    MALFORMED: malformed,
  });
}

function renderEconomics(t: Template, e: Report['economics']): string {
  const stat = (VALUE: string, LABEL: string) =>
    fill(t['econ-stat'] as string, { VALUE, LABEL });

  const decisions = e.decidedByProbe + e.decidedByAgent;
  const tokenLabel = e.tokensEstimated ? 'estimated tokens' : 'tokens';

  const stats = [
    stat(num(e.decidedByProbe), 'decided by probe'),
    stat(num(e.decidedByAgent), 'decided by agent'),
    stat(
      decisions === 0 ? 'n/a' : `${pct(e.decidedByProbe, decisions).toFixed(0)}%`,
      'probe-decided share',
    ),
    stat(`${num(e.nodesSampled)} / ${num(e.nodesTotal)}`, 'nodes judged / gathered'),
    stat(num(e.tokensIn), `${tokenLabel} in`),
    stat(num(e.tokensOut), `${tokenLabel} out`),
    stat(duration(e.wallClockMs), 'wall clock'),
    stat(num(e.probesMinted), 'probes minted'),
    stat(num(e.probeLibrarySize), 'probe library size'),
  ].join('');

  const notes: string[] = [];
  if (e.tokensEstimated) {
    notes.push(
      'Token counts are estimated, and labelled so: a skill running inside an agent session has no API for its own usage, so the figure is ceil(chars/4) over the judgment payloads and responses. Wall clock and probe-decided share are measured directly.',
    );
  }
  if (e.nodesSampled !== e.nodesTotal) {
    notes.push(
      `${num(e.nodesSampled)} of ${num(e.nodesTotal)} gathered edges were judged — the cap is printed here and beside the ratio, never applied silently.`,
    );
  }
  if (e.probeLibrarySize === 0) {
    notes.push(
      'The probe library is empty, so every decision on this run cost a model call. That is the left-hand end of the crystallization curve, not a defect.',
    );
  }

  return fill(t.econ as string, { STATS: stats, NOTE: notes.join(' ') });
}

// ---------------------------------------------------------------------------
// Loading
// ---------------------------------------------------------------------------

const HERE = import.meta.dir;

export function loadTemplate(path = join(HERE, '..', 'templates', 'report.html')): Template {
  const blocks = parseTemplate(readFileSync(path, 'utf8'));
  const required = [
    'document',
    'header',
    'ratio',
    'verdict',
    'scope',
    'econ',
    // Both, not either: `audit` alone would let a template ship that renders a
    // rate when there is one and silently nothing when there is not, which is
    // the defect this pair exists to close.
    'audit',
    'audit-none',
    // Same argument one scope down: without these, a template could ship that
    // renders unreadable audits as agreement (or as nothing) instead of naming
    // them, which is the fail-open this pair exists to close.
    'audit-malformed',
    'verdict-audit-malformed',
    // EVERY auxiliary block, not the headline ones only. Each of these renders
    // for one specific report shape, so a template missing one loads fine, most
    // reports render fine, and the shape that needed it emits `undefined` or
    // throws — a defect that surfaces on the least common input, which is the
    // worst possible time. Loading is the cheap place to find out.
    'audit-coverage',
    'audit-coverage-none',
    'audit-disagreement',
    'audit-nonprobe',
    'audit-nonprobe-only',
    'verdict-audit',
    'verdict-audit-disagreed',
  ];
  const missing = required.filter((b) => !(b in blocks));
  if (missing.length > 0) {
    throw new Error(`${path}: template is missing block(s): ${missing.join(', ')}`);
  }
  return blocks;
}

/**
 * Both stylesheets, verbatim, in one string. They are written to be inlined —
 * no `@import`, no webfont, no external reference — which is the only reason
 * the zero-external-request invariant is reachable at all.
 */
export function loadStyles(dir = join(HERE, '..', 'design')): string {
  const tokens = readFileSync(join(dir, 'tokens.css'), 'utf8');
  const keel = readFileSync(join(dir, 'keel.css'), 'utf8');
  return `${tokens}\n${keel}`;
}

/**
 * Read a gather-coverage sibling.
 *
 * Validated on arrival rather than trusted: this file is written by a producer
 * the report does not vouch for, and the one thing worse than no blindness card
 * is a blindness card asserting a shape nobody checked. `schema` is required —
 * an unlabelled JSON blob next to a report is not evidence about coverage — and
 * every list must be an array of the entries the card will read. Anything else
 * comes back `rejected` and is disclosed on the page, never dropped.
 *
 * Each list gets its OWN predicate, checking every field the card dereferences.
 * A single shared "has a string `path`" test was the whole validation, and it
 * accepted an unread entry with no `tool` and no `kind` — which the card then
 * printed as the literal text `undefined` in the tool column of a table whose
 * subject is what this run could not see. Validation that advertises a shape and
 * checks one field of it is the ungrounded check this tool is named after,
 * committed here.
 */
export function loadCoverage(
  path: string,
): { coverage: GatherCoverage } | { rejected: string } | null {
  if (!existsSync(path)) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return { rejected: path };
  }
  const c = parsed as Partial<GatherCoverage> | null;
  const str = (v: unknown): boolean => typeof v === 'string';
  const listOf = (
    list: unknown,
    ok: (e: Record<string, unknown>) => boolean,
  ): boolean =>
    Array.isArray(list) &&
    list.every(
      (e) =>
        e !== null && typeof e === 'object' && !Array.isArray(e) && ok(e as Record<string, unknown>),
    );
  if (
    c === null ||
    typeof c !== 'object' ||
    Array.isArray(c) ||
    c.schema !== 'keel.gather-coverage.v1' ||
    typeof c.target !== 'string' ||
    typeof c.nodesGathered !== 'number' ||
    !listOf(
      c.unread,
      (e) => str(e.path) && str(e.tool) && (e.kind === 'file' || e.kind === 'dir'),
    ) ||
    !listOf(c.silent, (e) => str(e.path) && str(e.parser)) ||
    !listOf(c.blind, (e) => str(e.path) && str(e.by) && str(e.reason))
  ) {
    return { rejected: path };
  }
  return { coverage: c as GatherCoverage };
}

/** Read a curve fragment, refusing it if inlining would break the invariant. */
export function loadCurve(
  path: string,
): { svg: string } | { rejected: string } | null {
  if (!existsSync(path)) return null;
  const svg = readFileSync(path, 'utf8');
  if (SVG_EXTERNAL_REF.test(svg)) return { rejected: path };
  return { svg };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE = `usage: bun scripts/render.ts <report.json> [-o <out.html>] [--curve <curve.svg>] [--no-curve] [--coverage <coverage.json>] [--no-coverage]

  <report.json>   a Report (see schemas/keel.ts)
  -o, --out       write here instead of stdout
  --curve         inline this SVG fragment at the KEEL:CURVE marker
  --no-curve      do not look for reports/curve.svg
  --coverage      the gather-coverage record for this run (gather.ts --coverage)
  --no-coverage   do not look for the sibling coverage record

With no --curve, reports/curve.svg is used if it exists (relative to the
current directory, then to the skill root). The KEEL:CURVE marker is emitted
either way.

With no --coverage, <report>.coverage.json beside the report is used if it
exists. Without one, the report cannot say which surfaces the gatherer failed
to read, and no blindness card is drawn — absence of the record is not a claim
that nothing was missed.`;

function main(argv: string[]): number {
  const args = argv.slice(2);
  if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
    console.log(USAGE);
    return args.length === 0 ? 1 : 0;
  }

  let input = '';
  let out = '';
  let curvePath = '';
  let noCurve = false;
  let coveragePath = '';
  let noCoverage = false;

  for (let i = 0; i < args.length; i++) {
    const a = args[i] as string;
    if (a === '-o' || a === '--out' || a === '--curve' || a === '--coverage') {
      // A flag whose value is missing, empty, or another flag is an error, not
      // a default. `-o "$OUT"` with an unset $OUT used to fall through to
      // stdout and exit 0: no file written, 87KB on the caller's terminal, and
      // a success code saying the report was produced. This tool refuses to
      // print a number it did not measure; it does not get to report a write
      // it did not perform either.
      const value = args[i + 1];
      if (value === undefined || value === '' || value.startsWith('-')) {
        console.error(`render: ${a} requires a path\n\n${USAGE}`);
        return 1;
      }
      i++;
      if (a === '--curve') curvePath = value;
      else if (a === '--coverage') coveragePath = value;
      else out = value;
    } else if (a === '--no-curve') noCurve = true;
    else if (a === '--no-coverage') noCoverage = true;
    else if (a.startsWith('-')) {
      console.error(`render: unknown flag ${a}\n\n${USAGE}`);
      return 1;
    } else input = a;
  }

  if (!input) {
    console.error(`render: no report given\n\n${USAGE}`);
    return 1;
  }
  if (!existsSync(input)) {
    console.error(`render: ${input}: no such file`);
    return 1;
  }

  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(input, 'utf8'));
  } catch (err) {
    console.error(`render: ${input}: not valid JSON — ${(err as Error).message}`);
    return 1;
  }
  // The shape is checked before anything is dereferenced. `null`, `7` and
  // `"a"` are all valid JSON, and reaching for `.nodes` on one of them threw a
  // raw TypeError with a Bun banner underneath it — the same exit code as the
  // tidy one-line refusal every other bad input gets, but it reads as a broken
  // tool rather than a rejected file.
  const shaped =
    parsed !== null &&
    typeof parsed === 'object' &&
    !Array.isArray(parsed) &&
    Array.isArray((parsed as Report).nodes) &&
    Array.isArray((parsed as Report).verdicts);
  if (!shaped) {
    console.error(
      `render: ${input}: not a Report — \`nodes\` and \`verdicts\` must both be arrays`,
    );
    return 1;
  }
  const report = parsed as Report;

  const opts: RenderOptions = {};
  if (!noCurve) {
    const candidates = curvePath
      ? [curvePath]
      : [resolve('reports/curve.svg'), resolve(HERE, '../reports/curve.svg')];
    for (const c of candidates) {
      const found = loadCurve(c);
      if (!found) continue;
      if ('svg' in found) {
        opts.curveSvg = found.svg;
      } else {
        opts.curveRejectedPath = found.rejected;
        console.error(
          `render: ${found.rejected} references something off-origin — not inlined`,
        );
      }
      break;
    }
    if (curvePath && !opts.curveSvg && !opts.curveRejectedPath) {
      console.error(`render: ${curvePath}: no such file — rendering the marker alone`);
    }
  }

  if (!noCoverage) {
    // Sibling of the report, the way the curve is a sibling of the run. The
    // default name is derived from the report's own path so that a directory of
    // reports pairs unambiguously — a single `coverage.json` per directory
    // would silently attach one target's blind spots to another's number.
    const sibling = coveragePath || `${input.replace(/\.json$/, '')}.coverage.json`;
    const found = loadCoverage(sibling);
    if (found && 'coverage' in found) {
      opts.coverage = found.coverage;
    } else if (found) {
      opts.coverageRejectedPath = found.rejected;
      console.error(
        `render: ${found.rejected} is not a keel.gather-coverage.v1 record — not used`,
      );
    } else if (coveragePath) {
      console.error(`render: ${coveragePath}: no such file`);
      return 1;
    } else {
      console.error(
        `render: no coverage record at ${sibling} — this report cannot state which surfaces the gatherer could not read (bun scripts/gather.ts <target> --coverage ${sibling})`,
      );
    }
  }

  let html: string;
  try {
    html = render(report, opts);
  } catch (err) {
    console.error(`render: ${(err as Error).message}`);
    return 1;
  }

  if (out) {
    mkdirSync(dirname(resolve(out)), { recursive: true });
    writeFileSync(out, html);
    const g = groundingRatio(report.verdicts);
    const denom = g.anchored + g.selfReferential + g.unknown;
    console.error(
      `wrote ${out} — ${report.nodes.length} node(s), ` +
        (denom === 0
          ? 'no denominator'
          : `ratio ${g.ratio.toFixed(2)} (${g.anchored}/${denom} anchored)`) +
        `, ${g.notACheck} not_a_check excluded`,
    );
  } else {
    console.log(html);
  }
  return 0;
}

if (import.meta.main) process.exit(main(process.argv));
