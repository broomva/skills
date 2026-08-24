/**
 * What `render.ts` emits must be PARSEABLE, not merely path-free.
 *
 * This file exists because of a bug that every other gate waved through. A
 * publish step rewrote machine-local absolute paths to a `<repo>` placeholder —
 * correct in intent, and the path-portability gate went green precisely because
 * the private path was genuinely gone. But the substitution ran over
 * already-rendered HTML, so the bare angle brackets landed inside the
 * crystallization curve's SVG `<desc>`. A lenient HTML parser read `<repo>` as
 * an unknown element and adopted every following sibling as its child: the
 * 1080x1510 chart reserved its full height and painted nothing at all.
 *
 * Nothing caught it. `bun test` passed, `tsc` passed, and the failure was
 * invisible in the HTML source — the page looked fine to everything except a
 * human looking at the pixels. By Keel's own vocabulary the old arrangement was
 * `not_a_check` for this property: no gate asserted anything about whether the
 * markup still described a drawing.
 *
 * WHAT IT MEASURES NOW. The publish step and the site it wrote were not carried
 * into the monorepo, so the original subject is gone. The property is not: it
 * belongs to the renderer, which ships. This file now renders a real Report
 * through the real `render.ts` and parses THAT — the artifact users actually
 * get, one step earlier in the same chain, and the step that was always the
 * more load-bearing of the two.
 *
 * WHY PYTHON DECIDES. Bun exposes no XML parser, and adding a dependency for
 * one check would break the zero-runtime-dependency rule. Hand-rolling a parser
 * here would be worse than either: the assertion would then rest on markup
 * logic this project also wrote, which is `self_referential` by its own
 * definition. `python3` is already a toolchain dependency, and `xml.etree` is a
 * parser nobody here maintains — so the verdict below is `anchored`, and it is
 * not arguable.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const ROOT = join(import.meta.dir, '..');
const RENDER = join(ROOT, 'scripts', 'render.ts');
const CURVE = join(ROOT, 'reports', 'curve.svg');

/**
 * Render every committed Report we have into one directory, then parse the
 * results. The corpus reports are real measured output, so this exercises the
 * renderer over the shapes it actually meets rather than over one hand-made
 * fixture. `curve.svg` is passed explicitly: a curve that fails to inline is
 * the exact failure being guarded, and letting the renderer fall back to "no
 * curve found" would turn that failure into a silent pass.
 */
function renderPages(): string {
  const out = mkdtempSync(join(tmpdir(), 'keel-markup-'));
  const inputs = [
    join(ROOT, 'tests', 'fixtures', 'report.sample.json'),
    join(ROOT, 'reports', 'keel.json'),
    join(ROOT, 'reports', 'openai-python.json'),
  ].filter((p) => existsSync(p));

  for (const input of inputs) {
    const name = `${input.split('/').pop()?.replace(/\.json$/, '')}.html`;
    const r = Bun.spawnSync({
      cmd: ['bun', RENDER, input, '--curve', CURVE, '-o', join(out, name)],
      stdout: 'pipe',
      stderr: 'pipe',
    });
    if (r.exitCode !== 0) {
      throw new Error(`render ${input} failed: ${r.stderr.toString()}`);
    }
  }
  return out;
}

const SITE = renderPages();

// Every other suite here routes its temp dirs through `tree()` in
// tests/helpers/tree.ts, which records them and drops them in an afterAll. This
// file renders directly instead — it needs real Reports, not a synthetic tree —
// and so has to do its own housekeeping. It did not, and left one directory of
// rendered HTML behind per run.
afterAll(() => {
  rmSync(SITE, { recursive: true, force: true });
});

const CHECKER = `
import json, pathlib, re, sys
import xml.etree.ElementTree as ET

site = pathlib.Path(sys.argv[1])
out = {}
for f in sorted(site.glob('*.html')):
    html = f.read_text()
    islands = re.findall(r'<svg\\b[\\s\\S]*?</svg>', html)
    rec = {'islands': len(islands), 'errors': [], 'rawPlaceholder': bool(re.search(r'<repo>|<home>', html)), 'curvePolylines': None}
    for svg in islands:
        try:
            root = ET.fromstring(svg)
        except ET.ParseError as e:
            rec['errors'].append(str(e))
            continue
        if 'keel-curve' in (root.get('class') or ''):
            # Count polylines that are reachable as descendants of the SVG root.
            # Under the bug these were nested inside a <repo> element, which is
            # not in the SVG namespace, so nothing under it renders.
            ns = '{http://www.w3.org/2000/svg}'
            rec['curvePolylines'] = len(root.findall('.//' + ns + 'polyline')) + len(root.findall('.//polyline'))
            foreign = sorted({
                el.tag for el in root.iter()
                if isinstance(el.tag, str) and not el.tag.startswith(ns) and el.tag not in ('style',)
            })
            if foreign:
                rec['errors'].append('foreign elements in curve: ' + ', '.join(foreign))
    out[f.name] = rec
print(json.dumps(out))
`;

type Rec = {
  islands: number;
  errors: string[];
  rawPlaceholder: boolean;
  curvePolylines: number | null;
};

const proc = Bun.spawnSync({
  cmd: ['python3', '-c', CHECKER, SITE],
  stdout: 'pipe',
  stderr: 'pipe',
});

if (proc.exitCode !== 0) {
  throw new Error(`markup checker failed: ${proc.stderr.toString()}`);
}

const report: Record<string, Rec> = JSON.parse(proc.stdout.toString());
const pages = Object.keys(report);

describe('rendered report markup', () => {
  test('there are pages to check at all', () => {
    // Guards against this whole file silently passing on an empty directory —
    // a suite that asserts nothing about nothing is the shape it exists to catch.
    expect(pages.length).toBeGreaterThan(0);
  });

  for (const page of pages) {
    const rec = report[page];

    test(`${page} — no raw path placeholder survives into markup`, () => {
      // The escaped form is the only correct one at the HTML boundary. A bare
      // one is an element, not a placeholder.
      expect(rec.rawPlaceholder).toBe(false);
    });

    test(`${page} — every inline SVG parses, with no foreign elements`, () => {
      expect(rec.errors).toEqual([]);
    });
  }

  test('the crystallization curve actually draws something', () => {
    // Asserting the <svg> is PRESENT would have passed all the way through the
    // bug — the element was always there, at full height, drawing nothing.
    const withCurve = pages.filter((p) => report[p].curvePolylines !== null);
    expect(withCurve.length).toBeGreaterThan(0);

    for (const page of withCurve) {
      expect(report[page].curvePolylines, `${page} curve polylines`).toBeGreaterThan(0);
    }
  });
});
