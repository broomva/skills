import type { Metadata } from "next";
import { Nav } from "../../components/Nav";
import { type Beat, ScrollCinemaStage } from "../../components/ScrollCinemaStage";
import { REPO } from "../../lib/repo";
import "./scroll-cinema.css";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Parallax — the branch that held",
  description:
    "One recorded trunk, eight simulated branches, and the one whose invariant held. A scroll-driven account of what Parallax actually enforces: propose, accept, fork, check, and type every answer observed or simulated.",
};

/**
 * Six beats. Each one is a claim the runtime enforces in code, in the order a
 * reader meets them, and each is the whole beat on its own — the footage
 * underneath is texture and the map beside it is a diagram, so a reader who
 * gets neither still gets the argument.
 */
const BEATS: Beat[] = [
  {
    id: "recorded",
    title: "Every operating decision is taken once.",
    body: "You change a price, a policy, an escalation threshold. The world moves, and the version where you chose differently is never observed. There is no staging environment for the way a business operates.",
  },
  {
    id: "now",
    title: "So stop at the last moment you know is real.",
    body: "Everything to the left of here happened and is tagged observed. Everything to the right has to earn the right to be believed, and this is the line the product is built around.",
  },
  {
    id: "proposal",
    title: "Parallax proposes a model of what is already in there.",
    body: "Point it at a directory, an agent's workspace or a set of tables. It comes back with state, actions, and the questions it could not answer — and the slots it cannot support come back empty rather than plausible.",
  },
  {
    id: "accept",
    title: "Nothing runs until you accept it.",
    body: "The accept gate is a runtime check, not a type-system convention. While a blocking question is open it refuses to activate, and a numeric quantity with no unit is always blocking.",
  },
  {
    id: "divergence",
    title: "Then fork the history and change one decision.",
    body: "Same initial state, same seed, the same twelve steps — one policy different. The log is append-only with copy-on-write, so a branch costs nothing to create and every branch is rolled forward and checked.",
  },
  {
    id: "held",
    title: "One branch held. And every number says how much of it was real.",
    body: "Not the branch with the most agreeable number — the one whose conservation invariant held for the whole run, checked by code rather than judged by a model. Typed observed or simulated at birth, carried into the receipt.",
  },
];

const CLIPS = ["01-recorded", "02-now", "03-proposal", "04-accept", "05-divergence", "06-held"].map(
  (id) => `${base}/scroll-cinema/${id}.mp4`,
);

// clips.length + 1 — one per seam, which is what the scrubber requires
const POSTERS = Array.from(
  { length: CLIPS.length + 1 },
  (_, i) => `${base}/scroll-cinema/p${String(i).padStart(2, "0")}.webp`,
);

export default function ScrollCinemaPage() {
  return (
    <div className="sc-page">
      <ScrollCinemaStage beats={BEATS} clips={CLIPS} posters={POSTERS} />

      <div id="main">
        <Nav base={base} />
        <section className="sc-out">
          <div className="wrap">
            <p className="lab">What you just watched</p>
            <h2>Six claims, and not one of them is a thing we are asking you to take on trust.</h2>
            <p className="t">
              A simulator&rsquo;s output is unfalsifiable by default: it produces confident numbers
              about a world that does not exist, and the usual answer is to claim more fidelity,
              which nobody can check inside a conversation. The design target here is not a
              simulator that is right. It is a simulator that cannot lie about being a simulator.
            </p>

            <ul className="sc-ledger">
              <li>
                <p className="k">The gate</p>
                <p className="v">
                  <code>activate()</code> refuses while a blocking question is open. The accepted
                  object is minted behind a module-private symbol and checked at runtime, so it
                  cannot be forged.
                </p>
              </li>
              <li>
                <p className="k">The fork</p>
                <p className="v">
                  Ungoverned, the demo storefront oversells stock it does not have ten times in
                  twelve steps. Forked one step before the damage with a governor installed: zero.
                </p>
              </li>
              <li>
                <p className="k">The typing</p>
                <p className="v">
                  Derivation joins the tags. One simulated input makes the answer simulated, all the
                  way to the top line, so a figure cannot be quoted as a measurement by accident.
                </p>
              </li>
              <li>
                <p className="k">The proof</p>
                <p className="v">
                  A policy cannot certify its own reproducibility. Run it again against an identical
                  probe; if the trace hash moves, the branch withdraws its own claim.
                </p>
              </li>
            </ul>

            <p className="t" style={{ marginTop: 32 }}>
              Nothing here is calibrated against a real business, and there is no accuracy figure on
              this page, because we do not have one. The footage above is generated and carries no
              claim — every number in this project is printed by a command in the Parallax runtime
              at seed 42 over a horizon of twelve steps.
            </p>

            <div className="sc-acts">
              <a href={`${base}/`}>See the product</a>
              <a className="ghost" href={`${base}/proof/`}>
                Read the proof
              </a>
              <a className="ghost" href={REPO} rel="noopener">
                Read the source
              </a>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
