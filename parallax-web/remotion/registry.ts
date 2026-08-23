import { ACCEPT_GATE_DURATION, AcceptGate } from "./comps/AcceptGate";
import { FORK_DURATION, ForkDiverge } from "./comps/ForkDiverge";
import { OPERATOR_LOOP_DURATION, OperatorLoop } from "./comps/OperatorLoop";
import { PROVENANCE_DURATION, Provenance } from "./comps/Provenance";
import { REPLAY_DURATION, ReplayHash } from "./comps/ReplayHash";
import { FPS, H, W } from "./kit";

export type MotionId = "AcceptGate" | "ForkDiverge" | "Provenance" | "ReplayHash" | "OperatorLoop";

/**
 * One record per composition, so a section names a motion by id and cannot get
 * the duration or the aspect wrong. `still` is the frame reduced-motion and the
 * poster fall back to: late enough that the figure is finished, which is the
 * same rule the hero's --p: 1 default follows.
 */
export const MOTION = {
  AcceptGate: {
    component: AcceptGate,
    duration: ACCEPT_GATE_DURATION,
    still: ACCEPT_GATE_DURATION - 24,
    op: "propose → accept",
    meta: "activate() · runtime brand",
  },
  ForkDiverge: {
    component: ForkDiverge,
    duration: FORK_DURATION,
    still: FORK_DURATION - 24,
    op: "rollout → diff",
    meta: "seed 42 · horizon 12",
  },
  Provenance: {
    component: Provenance,
    duration: PROVENANCE_DURATION,
    still: PROVENANCE_DURATION - 24,
    op: "observe → receipt",
    meta: "observed | simulated",
  },
  ReplayHash: {
    component: ReplayHash,
    duration: REPLAY_DURATION,
    still: REPLAY_DURATION - 24,
    op: "traceHash → certify",
    meta: "PINNED · STABLE · RECORDED",
  },
  OperatorLoop: {
    component: OperatorLoop,
    duration: OPERATOR_LOOP_DURATION,
    still: OPERATOR_LOOP_DURATION - 30,
    op: "el bucle completo",
    meta: "observar → … → recalibrar",
  },
} as const satisfies Record<
  MotionId,
  {
    component: React.FC;
    duration: number;
    still: number;
    op: string;
    meta: string;
  }
>;

export const MOTION_FPS = FPS;
export const MOTION_W = W;
export const MOTION_H = H;
