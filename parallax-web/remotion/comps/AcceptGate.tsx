import { AbsoluteFill, useCurrentFrame } from "remotion";
import { at, C, Caption, ease, H, Mono, Rail, Stage, Tag, W } from "../kit";

/**
 * Claim 1 — an ontology nobody accepted cannot run.
 *
 * The beats are the real ones: proposeOntology reads a directory and emits a
 * record with empty slots where the context did not support one; activate()
 * refuses with BLOCKING_QUESTIONS_OPEN while a unit is missing; the accepted
 * object is minted behind a module-private symbol and checked at runtime.
 *
 * The seven questions are the seven the filesystem proposer actually raises --
 * one numeric parameter per top-level directory -- and they are all answered
 * with the same unit, because that is what honestly happens. The tool will not
 * guess `files`; a person types it.
 */

const GATE_X = 812;
const LANE_Y = 520;

// Four slots on the card and the rest as a footnote: at the size this panel is
// actually displayed, six rows plus a header is a wall of 15px type.
const SLOTS: Array<[string, string, string]> = [
  ["state", "14 fields", "fg"],
  ["actions", "7", "fg"],
  ["invariants", "— empty —", "faint"],
  ["blocking", "7", "warn"],
];

const QUESTIONS = [
  "src.count",
  "test.count",
  "docs.count",
  "scripts.count",
  "web.count",
  "design.count",
  "landing.count",
];

export const AcceptGate: React.FC = () => {
  const f = useCurrentFrame();

  // How many questions are answered by now: one every 9 frames from f=66.
  const answered = Math.max(0, Math.min(QUESTIONS.length, Math.floor((f - 66) / 9) + 1));
  const allAnswered = answered >= QUESTIONS.length;

  // The refusal: activate() is attempted at f=38 and bounces off a closed gate.
  const refuse = at(f, 40, 8) * (1 - at(f, 132, 10));

  // The gate opens once nothing is blocking. Two halves retract from the lane.
  const open = ease(f, 150, 22);
  const halfLen = 150;

  // The puck: refused travel, then a real crossing.
  const bump = Math.sin(Math.min(1, Math.max(0, (f - 40) / 10)) * Math.PI) * 92;
  const cross = ease(f, 178, 26);
  const puckX = 560 + bump + cross * (990 - 560);

  return (
    <AbsoluteFill>
      <Stage>
        <Rail left="OPERATOR · propose → accept" right="proposeOntology · activate" />

        {/* ---- the proposal record ---- */}
        <g opacity={at(f, 4)}>
          <rect x={64} y={168} width={496} height={380} rx={14} fill="none" stroke={C.rule} />
          <Tag x={92} y={212} fill={C.dim}>
            PROPOSAL
          </Tag>
          <Mono x={92} y={252} size={28} fill={C.faint}>
            kind filesystem · root ./
          </Mono>
          {SLOTS.map(([k, v, tone], i) => {
            const y = 306 + i * 54;
            const fill =
              tone === "warn" ? C.warn : tone === "faint" ? C.faint : tone === "dim" ? C.dim : C.fg;
            // the blocking count is the only number that moves
            const shown = k === "blocking" ? String(QUESTIONS.length - answered) : v;
            const done = k === "blocking" && allAnswered;
            return (
              <g key={k} opacity={at(f, 12 + i * 5)}>
                <Mono x={92} y={y} size={31} fill={C.tag}>
                  {k}
                </Mono>
                <Mono x={532} y={y} size={31} anchor="end" fill={done ? C.ok : fill}>
                  {done ? "0 · clear" : shown}
                </Mono>
              </g>
            );
          })}
          <Mono x={92} y={528} size={26} fill={C.faint}>
            advisory 1 · transition you supply
          </Mono>
        </g>

        {/* ---- the questions being answered ---- */}
        <g opacity={at(f, 60)}>
          <Tag x={64} y={672} fill={C.faint}>
            BLOCKING — NO UNIT, NO RUN
          </Tag>
          {QUESTIONS.map((q, i) => {
            const isDone = i < answered;
            const y = 716 + Math.floor(i / 2) * 46;
            const x = 64 + (i % 2) * 604;
            return (
              <g key={q} opacity={at(f, 62 + i * 4)}>
                <Mono x={x} y={y} size={28} fill={isDone ? C.faint : C.warn}>
                  {isDone ? "✓" : "?"}
                </Mono>
                <Mono x={x + 34} y={y} size={28} fill={isDone ? C.faint : C.dim}>
                  {q}
                </Mono>
                <Mono x={x + 330} y={y} size={28} fill={isDone ? C.ok : C.faint}>
                  {isDone ? "files" : "unit?"}
                </Mono>
              </g>
            );
          })}
        </g>

        {/* ---- the lane ---- */}
        <line
          x1={560}
          y1={LANE_Y}
          x2={1400}
          y2={LANE_Y}
          stroke={C.axis}
          strokeWidth={1}
          strokeDasharray="3 8"
        />

        {/* ---- the gate ---- */}
        <g opacity={1 - open}>
          <line
            x1={GATE_X}
            y1={LANE_Y - halfLen}
            x2={GATE_X}
            y2={LANE_Y - open * halfLen}
            stroke={C.accent}
            strokeWidth={5}
            strokeLinecap="round"
          />
          <line
            x1={GATE_X}
            y1={LANE_Y + open * halfLen}
            x2={GATE_X}
            y2={LANE_Y + halfLen}
            stroke={C.accent}
            strokeWidth={5}
            strokeLinecap="round"
          />
        </g>
        <g>
          <Tag x={GATE_X} y={LANE_Y - halfLen - 28} anchor="middle" fill={C.accent}>
            {open > 0.5 ? "ACCEPTED" : "ACCEPT GATE"}
          </Tag>
          <Mono
            x={GATE_X}
            y={LANE_Y + halfLen + 40}
            size={28}
            anchor="middle"
            fill={C.faint}
            opacity={1 - open}
          >
            runtime check, not a convention
          </Mono>
        </g>

        {/* ---- the refusal ---- */}
        <g opacity={refuse}>
          <Mono x={GATE_X - 34} y={LANE_Y + 74} size={32} anchor="end" fill={C.crit}>
            activate() → refused
          </Mono>
          <Mono x={GATE_X - 34} y={LANE_Y + 114} size={28} anchor="end" fill={C.crit}>
            BLOCKING_QUESTIONS_OPEN
          </Mono>
        </g>

        {/* ---- the puck ---- */}
        <g opacity={at(f, 34)}>
          <circle cx={puckX} cy={LANE_Y} r={13} fill={C.bg} stroke={C.fg} strokeWidth={3} />
          <Mono x={puckX} y={LANE_Y - 34} size={27} anchor="middle" fill={C.faint}>
            run
          </Mono>
        </g>

        {/* ---- what comes out the other side ---- */}
        <g opacity={at(f, 196)}>
          <rect
            x={1058}
            y={LANE_Y - 182}
            width={478}
            height={292}
            rx={14}
            fill={C.accentSoft}
            stroke={C.accent}
          />
          <Tag x={1088} y={LANE_Y - 132} fill={C.accent}>
            ACTIVE ONTOLOGY
          </Tag>
          <Mono x={1088} y={LANE_Y - 82} size={30} fill={C.fg}>
            brand ✓ module-private
          </Mono>
          <Mono x={1088} y={LANE_Y - 42} size={30} fill={C.fg}>
            checked at runtime
          </Mono>
          <Mono x={1088} y={LANE_Y + 4} size={27} fill={C.dim}>
            acceptedBy · at · proposal
          </Mono>
          <Mono x={1088} y={LANE_Y + 48} size={27} fill={C.faint}>
            does not survive JSON
          </Mono>
        </g>

        <Caption from={206}>Nothing ran until a person answered the seven open questions.</Caption>
      </Stage>
    </AbsoluteFill>
  );
};

export const ACCEPT_GATE_DURATION = 260;
export const ACCEPT_GATE_SIZE = { width: W, height: H };
