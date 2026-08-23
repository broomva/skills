import type { Event, State, TypeRecord } from "../core/types";

/**
 * A clinic appointment desk.
 *
 * This world exists to answer one objection: that the runtime is a storefront
 * simulator with extra steps. Nothing in src/core changed to support it. It is a
 * TypeRecord -- five slots of data -- and the six operators fold over it exactly
 * as they fold over the storefront.
 *
 * It was also chosen because its conservation identity is a DIFFERENT SHAPE from
 * the storefront's. The storefront conserves money and stock: scalar quantities
 * that go up and down. A clinic conserves *time against a roster*, which is
 * two-dimensional -- minutes are attached to a specific clinician in a specific
 * window, so the same total can be perfectly balanced and still impossible. A
 * runtime that only handled scalar conservation would pass the storefront and
 * fail here.
 */
interface Clinic extends State {
  /** minutes each clinician has available in the session */
  roster: Record<string, number>;
  /** minutes already committed per clinician */
  committed: Record<string, number>;
  /** every appointment ever booked and not cancelled */
  booked: Array<{ ref: string; clinician: string; start: number; minutes: number }>;
  cancelled: string[];
  attended: string[];
  no_show: string[];
  /** the session's bookable window, in minutes from open */
  window_minutes: number;
  revenue_cents: number;
  refunds_cents: number;
  collected_cents: number;
}

const initial: Clinic = {
  roster: { dr_ochoa: 240, dr_pineda: 180, nurse_rios: 120 },
  committed: { dr_ochoa: 0, dr_pineda: 0, nurse_rios: 0 },
  booked: [],
  cancelled: [],
  attended: [],
  no_show: [],
  window_minutes: 240,
  revenue_cents: 0,
  refunds_cents: 0,
  collected_cents: 0,
};

function transition(state: State, e: Event): State {
  const s = structuredClone(state) as Clinic;
  const p = e.params as Record<string, unknown>;
  const ref = p.ref as string;
  const clinician = p.clinician as string;

  switch (e.action) {
    case "book": {
      const minutes = (p.minutes as number) ?? 20;
      const start = (p.start as number) ?? 0;
      s.booked.push({ ref, clinician, start, minutes });
      s.committed[clinician] = (s.committed[clinician] ?? 0) + minutes;
      s.revenue_cents += (p.cents as number) ?? 0;
      return s;
    }
    case "cancel": {
      const appt = s.booked.find((b) => b.ref === ref);
      if (appt) {
        s.committed[appt.clinician] = (s.committed[appt.clinician] ?? 0) - appt.minutes;
        s.booked = s.booked.filter((b) => b.ref !== ref);
      }
      s.cancelled.push(ref);
      return s;
    }
    case "attend":
      s.attended.push(ref);
      s.collected_cents += (p.cents as number) ?? 0;
      return s;
    case "no_show":
      s.no_show.push(ref);
      return s;
    case "refund": {
      const cents = (p.cents as number) ?? 0;
      s.refunds_cents += cents;
      s.collected_cents -= cents;
      return s;
    }
    case "extend_roster":
      s.roster[clinician] = (s.roster[clinician] ?? 0) + ((p.minutes as number) ?? 0);
      return s;
    default:
      return s;
  }
}

/** Do two appointments for the same clinician overlap in time? */
function overlaps(
  a: { start: number; minutes: number },
  b: { start: number; minutes: number },
): boolean {
  return a.start < b.start + b.minutes && b.start < a.start + a.minutes;
}

export const clinic: TypeRecord = {
  slug: "clinic-appointment-desk",
  title: "Clinic appointment desk",
  initial,
  actions: [
    {
      name: "book",
      actor: "front-desk",
      params: {
        ref: "string",
        clinician: "string",
        start: "number",
        minutes: "number",
        cents: "number",
      },
      units: { start: "minutes_from_open", minutes: "minutes", cents: "COP_cents" },
    },
    { name: "cancel", actor: "front-desk", params: { ref: "string" } },
    {
      name: "attend",
      actor: "clinician",
      params: { ref: "string", cents: "number" },
      units: { cents: "COP_cents" },
    },
    { name: "no_show", actor: "front-desk", params: { ref: "string" } },
    {
      name: "refund",
      actor: "front-desk",
      params: { ref: "string", cents: "number" },
      units: { cents: "COP_cents" },
    },
    {
      name: "extend_roster",
      actor: "manager",
      params: { clinician: "string", minutes: "number" },
      units: { minutes: "minutes" },
    },
  ],
  invariants: [
    {
      name: "roster_not_oversold",
      kind: "conservation",
      // The scalar half: nobody is committed to more minutes than they have.
      check: (st) => {
        const s = st as Clinic;
        const over = Object.entries(s.committed).filter(
          ([who, mins]) => mins > (s.roster[who] ?? 0),
        );
        return over.length === 0
          ? null
          : `committed beyond roster: ${over
              .map(([w, m]) => `${w} ${m}/${s.roster[w] ?? 0}min`)
              .join(", ")}`;
      },
    },
    {
      name: "no_double_booking",
      kind: "safety",
      // The dimensional half a scalar ledger cannot see: the totals can balance
      // exactly and the schedule still be impossible, because a clinician cannot
      // be in two rooms at 10:20.
      check: (st) => {
        const s = st as Clinic;
        const clash: string[] = [];
        for (let i = 0; i < s.booked.length; i++) {
          for (let j = i + 1; j < s.booked.length; j++) {
            const a = s.booked[i];
            const b = s.booked[j];
            if (a && b && a.clinician === b.clinician && overlaps(a, b)) {
              clash.push(`${a.ref}/${b.ref}@${a.clinician}`);
            }
          }
        }
        return clash.length === 0 ? null : `same clinician in two places: ${clash.join(", ")}`;
      },
    },
    {
      name: "cash_conserved",
      kind: "conservation",
      /**
       * You cannot refund money you never took.
       *
       * The first version of this checked `collected_cents + refunds_cents >= 0`,
       * which is algebraically CONSTANT: `refund` decrements collected by exactly
       * what it adds to refunds, so the sum never moves from its initial value
       * and no sequence of events could make it negative. It read as a
       * conservation check and verified nothing.
       *
       * The reachability test found it. Reading the line never would have -- the
       * expression is correct arithmetic, it just cannot vary. That is the same
       * shape as the demotion function that shipped uncalled and the accept
       * brand that only existed at compile time, filed as
       * `a-gate-that-never-executes`, and it happened here an hour after filing
       * it.
       */
      check: (st) => {
        const s = st as Clinic;
        return s.collected_cents >= 0
          ? null
          : `refunded more than was ever collected: ${s.collected_cents} cents`;
      },
    },
    {
      name: "no_attendance_without_booking",
      kind: "policy",
      check: (st) => {
        const s = st as Clinic;
        const refs = new Set(s.booked.map((b) => b.ref));
        const ghost = s.attended.filter((r) => !refs.has(r));
        return ghost.length === 0 ? null : `attended without a live booking: ${ghost.join(", ")}`;
      },
    },
    {
      name: "booking_inside_the_session",
      kind: "safety",
      check: (st) => {
        const s = st as Clinic;
        const outside = s.booked.filter(
          (b) => b.start + b.minutes > s.window_minutes || b.start < 0,
        );
        return outside.length === 0
          ? null
          : `booked outside the session window: ${outside.map((b) => b.ref).join(", ")}`;
      },
    },
  ],
  transition,
};
