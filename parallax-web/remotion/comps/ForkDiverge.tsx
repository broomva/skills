import { AbsoluteFill, useCurrentFrame } from "remotion";
import { at, C, Caption, ease, H, Mono, Rail, Stage, Tag } from "../kit";

/**
 * Claim 2 — a history can be forked, and the angle between the branches is
 * the measurement. That is what the word parallax means.
 *
 * Both rays are DOTTED because dotted is the stroke for PINNED, and PINNED is
 * the class both branches actually demonstrated. Drawing the governed branch
 * solid would claim it was recorded. It was not; it was simulated, and the
 * whole point of the product is that the drawing has to say so.
 */

const X0 = 360; // seq 0, the fork
const X1 = 1290; // step 12 — the branch readouts live outside it
const Y0 = 772; // zero violations
const Y12 = 216; // twelve violations
const STEPS = 12;

const MAIN = [0, 0, 0, 0, 1, 2, 3, 4, 5, 7, 8, 9, 10];
const GOV = new Array(13).fill(0);

const px = (i: number) => X0 + (i / STEPS) * (X1 - X0);
const py = (v: number) => Y0 + (v / STEPS) * (Y12 - Y0);
const path = (series: number[]) =>
  series.map((v, i) => `${i === 0 ? "M" : "L"}${px(i)} ${py(v)}`).join(" ");

export const ForkDiverge: React.FC = () => {
  const f = useCurrentFrame();

  // The replay: 12 steps between f=84 and f=216.
  const run = ease(f, 84, 132);
  const head = run * STEPS;
  const shown = Math.min(STEPS, Math.floor(head + 0.0001));
  const headX = px(head);

  const mainNow = MAIN[shown] ?? 0;
  const done = head >= STEPS - 0.01;

  return (
    <AbsoluteFill>
      <Stage>
        <Rail left="OPERATOR · rollout → diff" right="seed 42 · horizon 12" />
        <Mono x={X1} y={158} size={30} anchor="end" fill={C.dim}>
          {`step ${shown} / ${STEPS}`}
        </Mono>

        <defs>
          <clipPath id="fk-sweep" clipPathUnits="userSpaceOnUse">
            <rect x={0} y={0} width={headX} height={H} />
          </clipPath>
        </defs>

        {/* ---- axes ---- */}
        <line x1={X0} y1={Y12 - 30} x2={X0} y2={Y0} stroke={C.axis} />
        <line x1={X0} y1={Y0} x2={X1 + 40} y2={Y0} stroke={C.axis} />
        <Tag x={72} y={150} anchor="start" fill={C.faint}>
          VIOLATIONS ACCUMULATED
        </Tag>
        {[0, 4, 8, 12].map((v) => (
          <g key={v}>
            <line x1={X0 - 8} y1={py(v)} x2={X1 + 40} y2={py(v)} stroke={C.grid} />
            <Mono x={X0 - 22} y={py(v) + 8} size={28} anchor="end" fill={C.faint}>
              {v}
            </Mono>
          </g>
        ))}
        {[0, 4, 8, 12].map((i) => (
          <Mono key={i} x={px(i)} y={Y0 + 38} size={28} anchor="middle" fill={C.faint}>
            {i === 0 ? "seq 0" : `step ${i}`}
          </Mono>
        ))}

        {/* ---- the recorded trunk: this part happened ---- */}
        <g opacity={at(f, 4)}>
          <line
            x1={112}
            y1={Y0}
            x2={X0}
            y2={Y0}
            stroke={C.fg}
            strokeWidth={4}
            strokeLinecap="round"
            strokeDasharray={248}
            strokeDashoffset={248 * (1 - ease(f, 6, 26))}
          />
          <Tag x={112} y={Y0 - 30} fill={C.tag}>
            RECORDED
          </Tag>
        </g>

        {/* ---- the fork ---- */}
        <g opacity={at(f, 34)}>
          <line
            x1={X0}
            y1={Y12 - 30}
            x2={X0}
            y2={Y0 + 20}
            stroke={C.faint}
            strokeWidth={1}
            strokeDasharray="3 7"
          />
          <circle cx={X0} cy={Y0} r={11} fill={C.bg} stroke={C.fg} strokeWidth={3} />
          <Tag x={X0} y={Y0 - 30} anchor="middle" fill={C.dim}>
            FORK
          </Tag>
        </g>

        {/* ---- what the fork changed, verbatim ---- */}
        <g opacity={at(f, 46)}>
          <Mono x={72} y={Y0 + 82} size={27} fill={C.crit}>
            − sales.policy ungoverned
          </Mono>
          <Mono x={72} y={Y0 + 118} size={27} fill={C.ok}>
            + sales.policy stock-governor
          </Mono>
        </g>

        {/* ---- the two branches ---- */}
        <g clipPath="url(#fk-sweep)">
          <path
            d={path(MAIN)}
            fill="none"
            stroke={C.fg}
            strokeOpacity={0.78}
            strokeWidth={4}
            strokeDasharray="2 10"
            strokeLinecap="round"
          />
          <path
            d={path(GOV)}
            fill="none"
            stroke={C.accent}
            strokeWidth={4}
            strokeDasharray="2 10"
            strokeLinecap="round"
          />
        </g>

        {/* ---- the playhead ---- */}
        <g opacity={at(f, 84) * (1 - at(f, 222, 14))}>
          <line x1={headX} y1={Y12 - 20} x2={headX} y2={Y0 + 12} stroke={C.faint} strokeWidth={1} />
        </g>

        {/* ---- live readouts, one per branch ---- */}
        <g opacity={at(f, 90)}>
          <Mono x={X1 + 46} y={py(MAIN[shown] ?? 0) - 14} size={35} fill={C.fg}>
            main
          </Mono>
          <Mono
            x={X1 + 46}
            y={py(MAIN[shown] ?? 0) + 20}
            size={30}
            fill={mainNow > 0 ? C.crit : C.faint}
          >
            {`${mainNow} oversold`}
          </Mono>
          <Mono x={X1 + 46} y={Y0 - 48} size={35} fill={C.accent}>
            governed
          </Mono>
          <Mono x={X1 + 46} y={Y0 - 14} size={30} fill={C.ok}>
            0 oversold
          </Mono>
        </g>

        {/* ---- the angle: the measurement ---- */}
        <g opacity={at(f, 224)}>
          <path
            d={`M${px(STEPS)} ${py(0)} L${px(STEPS)} ${py(MAIN[STEPS])} L${X0} ${Y0} Z`}
            fill={C.accentSoft}
          />
          <line
            x1={px(STEPS)}
            y1={py(0)}
            x2={px(STEPS)}
            y2={py(MAIN[STEPS])}
            stroke={C.accent}
            strokeWidth={2}
          />
          <Mono
            x={px(STEPS) - 24}
            y={(py(0) + py(MAIN[STEPS])) / 2}
            size={40}
            anchor="end"
            fill={C.accent}
          >
            Δ 10 → 0
          </Mono>
        </g>

        {done ? (
          <Caption from={236}>Same seed, same state, same steps. One policy different.</Caption>
        ) : null}
      </Stage>
    </AbsoluteFill>
  );
};

export const FORK_DURATION = 290;
