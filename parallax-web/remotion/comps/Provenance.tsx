import { AbsoluteFill, useCurrentFrame } from "remotion";
import { at, C, Caption, ease, Mono, Rail, Stage, Tag } from "../kit";

/**
 * Claim 3 — nothing in the system can produce a number without saying how
 * much of it was real.
 *
 * The rule being drawn is the join: an answer is observed only if every input
 * it was derived from was observed. One simulated input makes the answer
 * simulated, and that is why the total cannot be quoted as a measurement no
 * matter how much of the ledger above it was real.
 *
 * The five quantities satisfy the storefront's conservation law on purpose --
 * 120 opening less 34 accepted is 86 closing -- because a figure that violates
 * the invariant it is illustrating teaches the wrong thing.
 *
 * An earlier cut had the rows TRAVEL from the left column into the receipt.
 * It left the left two thirds of the stage empty at every frame after the
 * first second, and the motion said nothing the staggered timing does not.
 * Both columns are held now, and only the connector moves.
 */

type Row = { k: string; v: string; sim: boolean };

const ROWS: Row[] = [
  { k: "stock.opening", v: "120 units", sim: false },
  { k: "orders.accepted", v: "34 units", sim: true },
  { k: "orders.refused", v: "6 units", sim: true },
  { k: "stock.closing", v: "86 units", sim: true },
  { k: "revenue", v: "4 080 000 COP", sim: true },
];

const LX = 72; // left column
const RX = 908; // receipt column
const BOX = { x: 880, y: 182, w: 660, h: 620 };
const TOP = 300;
const GAP = 68;
const rowY = (i: number) => TOP + i * GAP;

export const Provenance: React.FC = () => {
  const f = useCurrentFrame();

  const born = (i: number) => at(f, 20 + i * 18);
  const lands = (i: number) => at(f, 62 + i * 18, 14);
  const landed = ROWS.filter((_, i) => lands(i) > 0.98).length;
  const simCount = ROWS.slice(0, landed).filter((r) => r.sim).length;
  const obsCount = landed - simCount;
  const split = landed === 0 ? 0 : simCount / landed;

  return (
    <AbsoluteFill>
      <Stage>
        <Rail left="OPERATOR · observe → receipt" right="every value carries its origin" />

        {/* ---- the key, stated before it is used ---- */}
        <g opacity={at(f, 4)}>
          <rect x={LX} y={148} width={18} height={18} rx={5} fill={C.ok} />
          <Mono x={LX + 32} y={164} size={28} fill={C.dim}>
            observed
          </Mono>
          <rect x={LX + 220} y={148} width={18} height={18} rx={5} fill={C.accent} />
          <Mono x={LX + 252} y={164} size={28} fill={C.dim}>
            simulated
          </Mono>
        </g>

        {/* ---- what the run produced ---- */}
        <Tag x={LX} y={250} fill={C.faint} opacity={at(f, 12)}>
          QUANTITIES
        </Tag>
        {ROWS.map((r, i) => {
          const tone = r.sim ? C.accent : C.ok;
          const y = rowY(i);
          return (
            <g key={r.k} opacity={born(i)}>
              <rect x={LX} y={y - 16} width={16} height={16} rx={4} fill={tone} />
              <Mono x={LX + 30} y={y} size={30} fill={C.fg}>
                {r.k}
              </Mono>
              <Mono x={LX + 640} y={y} size={30} anchor="end" fill={C.dim}>
                {r.v}
              </Mono>
              {/* the connector is the only thing that travels */}
              <line
                x1={740}
                y1={y - 8}
                x2={740 + 120 * lands(i)}
                y2={y - 8}
                stroke={tone}
                strokeWidth={2}
                strokeDasharray="2 7"
              />
            </g>
          );
        })}

        {/* ---- the receipt ---- */}
        <g opacity={at(f, 44)}>
          <rect
            x={BOX.x}
            y={BOX.y}
            width={BOX.w}
            height={BOX.h}
            rx={14}
            fill="none"
            stroke={C.rule}
          />
          <Tag x={RX} y={226} fill={C.dim}>
            RUN RECEIPT
          </Tag>
          <Mono x={1512} y={226} size={28} anchor="end" fill={C.accent}>
            class PINNED
          </Mono>
          <line x1={RX} y1={252} x2={1512} y2={252} stroke={C.rule} />
        </g>

        {ROWS.map((r, i) => {
          const tone = r.sim ? C.accent : C.ok;
          const y = rowY(i);
          return (
            <g key={`r-${r.k}`} opacity={lands(i)}>
              <Mono x={RX} y={y} size={30} fill={C.fg}>
                {r.k}
              </Mono>
              <Mono x={1430} y={y} size={30} anchor="end" fill={C.dim}>
                {r.v}
              </Mono>
              <Mono x={1450} y={y} size={27} fill={tone}>
                {r.sim ? "sim" : "obs"}
              </Mono>
            </g>
          );
        })}

        {/* ---- the join: why the total cannot be observed ---- */}
        <g opacity={at(f, 190)}>
          <line x1={RX} y1={620} x2={1512} y2={620} stroke={C.rule} />
          <Mono x={RX} y={664} size={30} fill={C.fg}>
            join(obs, sim × 4)
          </Mono>
          <Mono x={1512} y={664} size={30} anchor="end" fill={C.accent}>
            = simulated
          </Mono>
        </g>

        {/* ---- the split ---- */}
        <g opacity={at(f, 96)}>
          <Tag x={RX} y={718} fill={C.faint}>
            ORIGIN SPLIT
          </Tag>
          <rect x={RX} y={740} width={604} height={16} rx={8} fill={C.grid} stroke={C.rule} />
          <rect x={RX} y={740} width={604 * split} height={16} rx={8} fill={C.accent} />
          <Mono x={RX} y={790} size={30} fill={C.dim}>
            {`${simCount} simulated · ${obsCount} observed`}
          </Mono>
        </g>

        {/* ---- the point ---- */}
        <g opacity={at(f, 212)}>
          <Mono x={LX} y={686} size={35} fill={C.fg}>
            revenue 4 080 000 COP
          </Mono>
          <Mono x={LX} y={726} size={30} fill={C.accent}>
            simulated — not a measurement
          </Mono>
          <line
            x1={LX}
            y1={744}
            x2={LX + 540}
            y2={744}
            stroke={C.accent}
            strokeWidth={2}
            strokeDasharray={540}
            strokeDashoffset={540 * (1 - ease(f, 218, 20))}
          />
        </g>

        <Caption from={236}>The tag is welded on at birth and travels with the number.</Caption>
      </Stage>
    </AbsoluteFill>
  );
};

export const PROVENANCE_DURATION = 300;
