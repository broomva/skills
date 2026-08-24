import { AbsoluteFill, useCurrentFrame } from "remotion";
import { at, C, Caption, ease, Mono, Rail, Stage, Tag, W } from "../kit";

/**
 * Claim 4 — a policy cannot certify its own reproducibility.
 *
 * certifyPolicy runs a policy repeatedly against an identical probe and
 * compares trace hashes. What a policy declares about itself is not evidence.
 * The third row is the one that matters: a policy that declared PINNED and
 * demonstrated otherwise is demoted, and the demotion is written onto the
 * branch rather than reported to the caller and forgotten.
 *
 * The third pair diverges LATE, at character eleven, because that is how an
 * unpinned actor actually fails -- the first calls agree and the drift starts
 * once the unpinned source is first read.
 */

const ADV = 25.4; // monospace advance at 42px in the stack below
const HX = 536; // the notes under each label run to ~442; this is the clearance

type Probe = {
  label: string;
  note: string;
  a: string;
  b: string;
  verdict: string;
  tone: string;
  ok: boolean;
};

const PROBES: Probe[] = [
  {
    label: "same seed",
    note: "identical probe, twice",
    a: "bef312a9c40d17e2",
    b: "bef312a9c40d17e2",
    verdict: "PINNED holds",
    tone: C.ok,
    ok: true,
  },
  {
    label: "seed 43",
    note: "a different world",
    a: "bef312a9c40d17e2",
    b: "7c1a04f8de93b055",
    verdict: "diverges, as it should",
    tone: C.dim,
    ok: true,
  },
  {
    label: "unpinned actor",
    note: "declared PINNED",
    a: "bef312a9c40d17e2",
    b: "bef312a9c4d0a71f",
    verdict: "DEMOTED → STABLE",
    tone: C.warn,
    ok: false,
  },
];

const HASH = {
  font: `400 42px ui-monospace, SFMono-Regular, "SF Mono", Menlo, Monaco, Consolas, monospace`,
} as const;

const ROW_Y = [274, 464, 654];
const START = [26, 96, 166];

export const ReplayHash: React.FC = () => {
  const f = useCurrentFrame();

  return (
    <AbsoluteFill>
      <Stage>
        <Rail left="OPERATOR · traceHash → certifyPolicy" right="a claim is not evidence" />

        <g opacity={at(f, 4)}>
          <Mono x={72} y={172} size={35} fill={C.dim}>
            certifyPolicy — run it again against an identical probe and compare
          </Mono>
        </g>

        {PROBES.map((p, i) => {
          const s = START[i];
          const y = ROW_Y[i];
          // characters resolve left to right, so a late divergence reads as one
          const resolved = Math.floor(ease(f, s + 20, 34) * p.a.length + 0.001);
          const firstBad = [...p.a].findIndex((c, k) => c !== p.b[k]);
          const settled = resolved >= p.a.length;

          return (
            <g key={p.label} opacity={at(f, s)}>
              <line x1={72} y1={y - 62} x2={W - 72} y2={y - 62} stroke={C.rule} />
              <Mono x={72} y={y - 8} size={38} fill={C.fg}>
                {p.label}
              </Mono>
              <Mono x={72} y={y + 28} size={28} fill={C.faint}>
                {p.note}
              </Mono>

              {/* Two text runs per hash, not one node per character: the
                  stack is monospace, so a run starting at HX + firstBad * ADV
                  lands exactly where the character-by-character version put
                  it, and the reveal is a slice rather than a per-glyph
                  opacity. Fewer nodes, and no key derived from an index. */}
              {[p.a, p.b].map((h, rowIdx) => {
                const cut = firstBad < 0 ? h.length : firstBad;
                const ok = h.slice(0, Math.min(resolved, cut));
                const bad = resolved > cut ? h.slice(cut, resolved) : "";
                const y2 = y - 12 + rowIdx * 42;
                return (
                  <g key={rowIdx === 0 ? "probe-a" : "probe-b"}>
                    <text x={HX} y={y2} fill={C.fg} style={HASH}>
                      {ok}
                    </text>
                    {bad ? (
                      <text x={HX + cut * ADV} y={y2} fill={p.tone} style={HASH}>
                        {bad}
                      </text>
                    ) : null}
                  </g>
                );
              })}

              {/* the underline marks where the two stopped agreeing */}
              {firstBad >= 0 && settled ? (
                <line
                  x1={HX + firstBad * ADV - 3}
                  y1={y + 40}
                  x2={HX + p.a.length * ADV - 3}
                  y2={y + 40}
                  stroke={p.tone}
                  strokeWidth={2}
                  strokeDasharray={(p.a.length - firstBad) * ADV}
                  strokeDashoffset={(p.a.length - firstBad) * ADV * (1 - ease(f, s + 54, 14))}
                />
              ) : null}

              <g opacity={at(f, s + 58)}>
                <Mono x={W - 72} y={y - 8} size={35} anchor="end" fill={p.tone}>
                  {p.verdict}
                </Mono>
                <Mono x={W - 72} y={y + 28} size={28} anchor="end" fill={C.faint}>
                  {p.ok ? "no action" : "written onto the branch"}
                </Mono>
              </g>
            </g>
          );
        })}

        {/* ---- the demotion, as a value rather than a log line ---- */}
        <g opacity={at(f, 244)}>
          <rect
            x={72}
            y={772}
            width={940}
            height={112}
            rx={12}
            fill={C.accentSoft}
            stroke={C.accent}
          />
          <Tag x={100} y={812} fill={C.accent}>
            BRANCH gov-1 · UPDATED
          </Tag>
          <Mono x={100} y={854} size={32} fill={C.fg}>
            class PINNED → STABLE · reason unpinned actor
          </Mono>
        </g>

        <Caption from={262}>The system withdrew its own claim. Nobody had to notice.</Caption>
      </Stage>
    </AbsoluteFill>
  );
};

export const REPLAY_DURATION = 310;
