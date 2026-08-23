/**
 * The reality map: one recorded trunk, many candidate branches, one that held.
 *
 * The visual grammar — a fan of faint candidate paths, one picked out in the
 * accent, numbered columns, node dots at each crossing — is borrowed. The
 * claim is not. A map that highlights "the future you want" is a map of a
 * simulator that lets you choose your own answer, which is the exact posture
 * this project refuses. The highlighted path here is the branch whose
 * invariant HELD, which is a property of the run and not a preference.
 *
 * Every reveal is a clamp() over one custom property, --p, set by scroll. No
 * timers and no transitions, so the drawing cannot drift out of step with the
 * words beside it, and --p's @property initial value of 1 is a complete
 * diagram for no-JS and reduced-motion.
 */

const COLS = [232, 424, 616, 808, 1000];
const ROOT_X = 96;
const MID = 400;

/** Each branch is its y offset from the baseline at each of the five columns. */
const BRANCHES: Array<{ id: string; ys: number[]; held?: boolean }> = [
  { id: "b1", ys: [-96, -168, -232, -246, -250] },
  { id: "b2", ys: [-58, -96, -104, -150, -152] },
  { id: "b3", ys: [-22, -30, -76, -34, -36] },
  { id: "held", ys: [-6, -4, 44, -62, -64], held: true },
  { id: "b4", ys: [26, 34, 30, 40, 42] },
  { id: "b5", ys: [64, 96, 8, 118, 120] },
  { id: "b6", ys: [104, 168, 176, 196, 198] },
  { id: "b7", ys: [140, 214, 250, 268, 270] },
];

/** Smooth cubic through the column crossings, flat-tangented at each node. */
function curve(ys: number[]): string {
  const pts: Array<[number, number]> = [
    [ROOT_X, MID],
    ...COLS.map((x, i) => [x, MID + ys[i]] as [number, number]),
  ];
  let d = `M${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const dx = (x1 - x0) * 0.5;
    d += ` C${x0 + dx} ${y0}, ${x1 - dx} ${y1}, ${x1} ${y1}`;
  }
  // run flat off the right edge so the branches read as continuing, not stopping
  const [lx, ly] = pts[pts.length - 1];
  d += ` L${lx + 96} ${ly}`;
  return d;
}

export function RealityMap() {
  const held = BRANCHES.find((b) => b.held);
  return (
    <svg
      className="rmap"
      viewBox="0 0 1160 800"
      preserveAspectRatio="xMidYMid meet"
      role="img"
      aria-labelledby="rmap-t rmap-d"
    >
      <title id="rmap-t">
        One recorded trunk, eight simulated branches, and the one whose invariant held
      </title>
      <desc id="rmap-d">
        A solid line enters from the left and stops at a point marked NOW. That solid stroke is the
        RECORDED class: it is what actually happened. At NOW a bar stands across it, because nothing
        runs until a human accepts the model. Past NOW the line fans into eight dotted branches
        sharing that one baseline, drawn across five numbered steps. Dotted is the PINNED class:
        byte-identical on replay. Seven of the branches fade. One stays lit, and it is the branch
        whose conservation invariant held for the whole run — not the branch with the most agreeable
        number.
      </desc>

      <defs>
        {/* Branches are revealed by a clip sweeping out of NOW: a dashed
            stroke cannot also be drawn on with stroke-dashoffset, because both
            uses need the same property. */}
        <clipPath id="rmap-sweep" clipPathUnits="userSpaceOnUse">
          <rect className="rmap-sweeprect" y="0" height="800" />
        </clipPath>
        <linearGradient id="rmap-fade" x1="0" x2="1" y1="0" y2="0">
          <stop offset="0" stopColor="#fff" stopOpacity="0" />
          <stop offset="0.35" stopColor="#fff" stopOpacity="1" />
        </linearGradient>
        <mask id="rmap-past" maskUnits="userSpaceOnUse" x="0" y="360" width="200" height="80">
          <rect x="0" y="360" width="200" height="80" fill="url(#rmap-fade)" />
        </mask>
      </defs>

      {/* column rules and their numbers */}
      <g className="rmap-cols">
        {COLS.map((x, i) => (
          <g key={x} className="rmap-col">
            <line x1={x} y1={96} x2={x} y2={712} />
            <text x={x} y={72} textAnchor="middle">
              {String(i + 1).padStart(2, "0")}
            </text>
          </g>
        ))}
      </g>

      {/* the recorded trunk: this part happened */}
      <g className="b-trunk">
        <line className="rmap-trunk" x1={0} y1={MID} x2={ROOT_X} y2={MID} mask="url(#rmap-past)" />
        <text className="rmap-tag" x={8} y={MID - 26}>
          RECORDED
        </text>
      </g>

      {/* now, and the gate across it */}
      <g className="b-now">
        <line className="rmap-nowline" x1={ROOT_X} y1={120} x2={ROOT_X} y2={688} />
        <text className="rmap-tag" x={ROOT_X} y={104} textAnchor="middle">
          NOW
        </text>
      </g>
      <g className="b-gate">
        <line className="rmap-gate-halo" x1={ROOT_X} y1={MID - 60} x2={ROOT_X} y2={MID + 60} />
        <line className="rmap-gate" x1={ROOT_X} y1={MID - 60} x2={ROOT_X} y2={MID + 60} />
      </g>

      {/* the branches */}
      <g clipPath="url(#rmap-sweep)">
        {BRANCHES.map((b) => (
          <path
            key={b.id}
            className={`rmap-ray${b.held ? " held" : ""}`}
            d={curve(b.ys)}
            fill="none"
          />
        ))}
        {BRANCHES.map((b) =>
          COLS.map((x, i) => (
            <circle
              key={`${b.id}-${x}`}
              className={`rmap-node${b.held ? " held" : ""}`}
              cx={x}
              cy={MID + b.ys[i]}
              r={b.held ? 5 : 3.5}
            />
          )),
        )}
      </g>

      {/* the root, drawn last so nothing overlaps it */}
      <circle className="rmap-root" cx={ROOT_X} cy={MID} r={7} />

      {/* the verdict */}
      {held ? (
        <g className="b-held">
          <circle className="rmap-end" cx={COLS[4] + 96} cy={MID + held.ys[4]} r={6} />
          <text className="rmap-held" x={COLS[4] + 84} y={MID + held.ys[4] - 24} textAnchor="end">
            the branch that held
          </text>
        </g>
      ) : null}
    </svg>
  );
}

export const REALITY_MAP_BRANCHES = BRANCHES.length;
