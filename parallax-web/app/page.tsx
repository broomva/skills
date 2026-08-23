import { Cinema } from "../components/Cinema";
import { MotionPanel } from "../components/MotionPanel";
import { Nav } from "../components/Nav";
import { Surface } from "../components/Surface";
import { Verdict } from "../components/Verdict";
import { Wiring } from "../components/Wiring";
import { CLONE, REPO, RUNTIME } from "../lib/repo";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const HUB = "https://parallax-hub.onrender.com";
const proof = (hash: string) => `${base}/proof/${hash}`;

/**
 * Four features, each one a claim the runtime actually enforces, each paired
 * with the composition that draws the mechanism. The prose is not a caption
 * for the animation: it carries the whole claim on its own, because the panel
 * is client-side and a reader without JavaScript should lose the motion and
 * none of the argument.
 */
const FEATURES = [
  {
    id: "AcceptGate" as const,
    n: "01",
    kicker: "The gate",
    title: "An ontology nobody accepted cannot run.",
    body: [
      "Parallax reads your context and proposes a model of it — state, actions, and the questions it could not answer from what was there. Slots it cannot support come back empty rather than plausible.",
      "The accept gate is a runtime check, not a type-system convention. It refuses while any blocking question is open, and a unit on a numeric quantity is always blocking, because a number with no unit fails closed at materialisation and the proposer will not invent one.",
    ],
    note: (
      <>
        <b>activate()</b> → BLOCKING_QUESTIONS_OPEN. The accepted object is minted behind a
        module-private symbol and checked at runtime, so it cannot be forged and does not survive a
        JSON round-trip.
      </>
    ),
    alt: "A proposal with six slots stands on the left. Seven blocking questions are open, and a run attempt bounces off a closed gate with the code BLOCKING_QUESTIONS_OPEN. The questions are answered one at a time until the count reaches zero, the gate retracts, and an active ontology is minted on the far side carrying a runtime-checked brand.",
    link: ["See the gate mechanics", proof("#gate")] as const,
  },
  {
    id: "ForkDiverge" as const,
    n: "02",
    kicker: "The fork",
    title: "Fork the history and change exactly one thing.",
    body: [
      "Your operations already run on an append-only history, and a history can be forked. Copy-on-write means a branch costs nothing to create, so the question stops being whether to spend a week testing it.",
      "Same initial state, same seed, same twelve steps — one policy different. The angle between the two branches is the measurement, which is what the word parallax means.",
    ],
    note: (
      <>
        Under an ungoverned sales agent the storefront oversells stock it does not have{" "}
        <b>ten times</b> in twelve steps. Forked at the step before the damage, with a governor
        installed, the same twelve steps produce <b>zero</b>.
      </>
    ),
    alt: "A solid recorded trunk arrives at a fork. Past the fork two dotted branches replay the same twelve steps. The branch named main climbs to ten violations; the branch named governed stays flat on zero. A wedge between the two endpoints marks the difference of ten as the measurement.",
    link: ["See the trajectory figure", proof("#trajectory")] as const,
  },
  {
    id: "Provenance" as const,
    n: "03",
    kicker: "The typing",
    title: "No number leaves without saying how much of it was real.",
    body: [
      "Every value is typed observed or simulated at birth, and derivation joins the tags: an answer is observed only if every input it came from was observed. One simulated input makes the answer simulated, all the way to the top line.",
      "That is why a Parallax figure cannot be quoted as a measurement by accident. The origin is welded to the number, into the receipt and out through the API.",
    ],
    note: (
      <>
        The receipt states its own split unprompted — this run reports <b>0 of 12 steps observed</b>{" "}
        — alongside the branch class and what the policy declared against what it demonstrated.
      </>
    ),
    alt: "Five quantities arrive one at a time, each stamped observed or simulated, and travel into a run receipt. An origin split bar fills as they land. The total at the bottom is computed as the join of every input tag and comes out simulated, because one simulated input makes the answer simulated.",
    link: ["See what the receipt says", proof("#typing")] as const,
  },
  {
    id: "ReplayHash" as const,
    n: "04",
    kicker: "The proof",
    title: "A policy is not allowed to certify its own reproducibility.",
    body: [
      "Determinism is checkable in five seconds, so Parallax checks it rather than claiming it. certifyPolicy runs a policy repeatedly against an identical probe and compares trace hashes. Replay is a hash comparison, not an assurance.",
      "A policy that cannot reproduce its own output under a fixed seed is demoted whatever it declares about itself — and the demotion is written onto the branch rather than reported once and forgotten.",
    ],
    note: (
      <>
        Same seed → identical hash. Different seed → diverges, which is a different world and not a
        defect. An unpinned actor → the branch <b>withdraws its own reproducibility claim</b>,
        PINNED down to STABLE.
      </>
    ),
    alt: "Three probes run against an identical input. The first pair of trace hashes matches character for character and PINNED holds. The second, under a different seed, diverges immediately, which is expected. The third diverges at character eleven under an unpinned actor, and the branch record is rewritten from class PINNED to class STABLE.",
    link: ["See the reproducibility lattice", proof("#typing")] as const,
  },
];

const USES = [
  {
    n: "Operations",
    h: "A change you only get to make once",
    p: "A price, a refund policy, an escalation threshold. There is no staging environment for the way a business operates, so the usual way to find out is from a customer.",
    ask: "What happens to stock-outs if the sales agent can promise same-day?",
  },
  {
    n: "Agent governance",
    h: "Whether a governor would have caught it",
    p: "Point it at an agent's own workspace, replay the run it already did, and install the constraint you were considering. The branch says which steps it would have refused.",
    ask: "Which of these twelve steps would a stock governor have stopped?",
  },
  {
    n: "Capacity",
    h: "A schedule under a load it has not seen",
    p: "The clinic domain is an appointment desk with its own transition and its own conservation law. Seats, hours and slots conserve the same way money and stock do.",
    ask: "If two clinicians take leave, how many appointments miss their window?",
  },
  {
    n: "Rehearsal",
    h: "A directory you have not modelled yet",
    p: "No integration and no schema agreed in advance. One non-recursive read and a stat per entry, and what comes back is a proposal you can argue with.",
    ask: "What is this repository as a state machine, and what does it already conserve?",
  },
];

export default function Home() {
  return (
    <>
      <Cinema />

      <main className="after" id="main">
        <Nav base={base} />

        {/* ---------------- hero ---------------- */}
        <section className="hero" id="hero">
          <div className="wrap">
            <div className="badges">
              <span className="badge">Apache-2.0</span>
              <span className="badge">bstack · ontology simulation layer</span>
              <span className="badge live">
                <span className="dot" /> hub deployed
              </span>
            </div>
            <h1 className="h1">Simulation results you accept before they are active.</h1>
            <p className="sub">
              Point Parallax at a context. It proposes a model built from what is actually in there,
              waits for a human to accept it, and only then rolls it forward under the decisions you
              are considering. Every answer is typed observed or simulated.
            </p>
            <div className="actions">
              <a className="cta" href={REPO} rel="noopener">
                Read the source
              </a>
              <a className="cta ghost" href="#guarantees">
                See what it enforces
              </a>
            </div>
            <p className="install">
              <code>git clone {CLONE.replace("https://", "")}</code>
              <span>then</span>
              <code>cd skills/{RUNTIME}</code>
              <span>then</span>
              <code>bun install &amp;&amp; bun run demo</code>
            </p>
            <Verdict>
              The design target is not a simulator that is right. It is a simulator that cannot lie
              about being a simulator — and all three of the things that follow from that are
              enforced in code, not in documentation.
            </Verdict>
          </div>
        </section>

        {/* ---------------- features ---------------- */}
        <section id="guarantees">
          <div className="wrap wide">
            <p className="eyebrow">What it enforces</p>
            <h2 className="h">Four guarantees, each one a runtime check rather than a promise.</h2>
            <p className="lede">
              A simulator&rsquo;s output is unfalsifiable by default: it produces confident numbers
              about a world that does not exist. The usual response is to claim more fidelity, which
              cannot be checked from the outside at all. These four can.
            </p>

            <div className="featlist">
              {FEATURES.map((f, i) => (
                <div className={`feature${i % 2 === 1 ? " flip" : ""}`} key={f.id}>
                  <div className="f-copy">
                    <p className="eyebrow">
                      {f.n} · {f.kicker}
                    </p>
                    <h3 className="ft">{f.title}</h3>
                    {f.body.map((p) => (
                      <p className="fb" key={p.slice(0, 24)}>
                        {p}
                      </p>
                    ))}
                    <p className="f-note">{f.note}</p>
                    <a className="f-link" href={f.link[1]}>
                      {f.link[0]} →
                    </a>
                  </div>
                  <div className="f-media">
                    <MotionPanel id={f.id} alt={f.alt} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* ---------------- how it works ---------------- */}
        <section id="how">
          <div className="wrap">
            <p className="eyebrow">How it works</p>
            <h2 className="h">Five steps, and one of them is the product.</h2>
            <p className="lede">
              Parallax reads what is already there. It does not ask you to model your operation
              first, because the model is the thing it is supposed to produce.
            </p>

            <ol className="spine">
              <li>
                <span className="s-n">01</span>
                <span className="s-k">Point</span>
                <span className="s-t">
                  At a directory, an agent&rsquo;s own workspace, or a set of business tables.
                </span>
              </li>
              <li>
                <span className="s-n">02</span>
                <span className="s-k">Propose</span>
                <span className="s-t">
                  An ontology assembled from what is in there — state, actions, and the questions it
                  could not answer. Slots it cannot support come back empty.
                </span>
              </li>
              <li className="gate">
                <span className="s-n">03</span>
                <span className="s-k">Accept</span>
                <span className="s-t">
                  <b className="s-lead">A human answers the blocking questions and accepts.</b> This
                  is the product, not a formality. Nothing runs before it.
                </span>
              </li>
              <li>
                <span className="s-n">04</span>
                <span className="s-k">Roll</span>
                <span className="s-t">
                  Fork the log at a point, change one decision, replay the same steps under the new
                  policy.
                </span>
              </li>
              <li>
                <span className="s-n">05</span>
                <span className="s-k">Type</span>
                <span className="s-t">
                  Every value carries observed or simulated, plus a class saying whether it can be
                  re-derived at all.
                </span>
              </li>
            </ol>

            <h3 className="mlab" style={{ marginTop: 48 }}>
              Three context classes, one intake
            </h3>
            <div className="grid3">
              <div className="cell">
                <p className="k">Class 01 — business data</p>
                <h3>A schema and its rows</h3>
                <p className="t">
                  Orders, ledgers, inventory, tickets. One state field and one insert action per
                  table, and a blocking question per numeric parameter. The conservation identity is
                  usually already in there — money, stock, hours, seats.
                </p>
              </div>
              <div className="cell">
                <p className="k">Class 02 — agent workspace</p>
                <h3>An agent&rsquo;s own directory</h3>
                <p className="t">
                  The session is spawned with its working directory already set to the
                  tenant&rsquo;s own folder, and the confinement keys off exactly that. Passing a
                  derived path instead is denied.
                </p>
              </div>
              <div className="cell">
                <p className="k">Class 03 — local filesystem</p>
                <h3>An arbitrary directory</h3>
                <p className="t">
                  Files, commits, exports, logs. No integration and no schema agreed in advance.
                  Same proposer as the workspace class; the difference is who is allowed to name the
                  root.
                </p>
              </div>
            </div>

            <Verdict>
              You are approving a model of your own operation, not a model&rsquo;s opinion of it. An
              empty slot is the correct answer when the context does not support one; a plausible
              guess is not.
            </Verdict>
          </div>
        </section>

        {/* ---------------- the agent is a user ---------------- */}
        <section id="surface">
          <div className="wrap">
            <p className="eyebrow">For agents</p>
            <h2 className="h">The agent is a user, not a client library.</h2>
            <p className="lede">
              Every capability a human can reach is reachable programmatically, over the same
              handler functions. Every failure is a value with a stable machine-readable code rather
              than a thrown string a caller has to parse, and the error types are per-operation: a
              plugin failure inside a rollout carries a partial trajectory, the same failure at
              registration carries nothing, and a single error type cannot express that difference.
            </p>
            <Surface />
            <p className="body" style={{ marginTop: 32 }}>
              The surfaces diverge in exactly two places, and both are confinement rather than
              capability. <code>--root</code>: an arbitrary absolute root is safe at a terminal,
              because the person typing the path is the confinement. It is absent from every tool
              schema, because inside a sandboxed session a derived path is denied and a denied read
              comes back as an empty directory rather than an error — so a wrong path would look
              like an empty workspace. And <code>--out</code> on <code>receipt</code>, which writes
              the page to a path the tool surface returns but never sends, because a receipt is tens
              of kilobytes and does not belong in a context window.
            </p>
            <p className="body" style={{ marginTop: 20 }}>
              That count is not a promise in prose. A test asserts every tool has exactly one CLI
              command, every command has a tool behind it, and every flag maps to a tool field or to
              one of those two named divergences — so widening the claim means editing a test that
              says so. It was written because the claim had been wrong: three tools had no CLI
              command at all.
            </p>
          </div>
        </section>

        {/* ---------------- the channel ---------------- */}
        <section id="channel">
          <div className="wrap">
            <p className="eyebrow">The channel</p>
            <h2 className="h">It reaches people where the business already runs.</h2>
            <p className="lede">
              An operator does not open a console. A real WhatsApp message already runs an agent
              turn in a confined workspace on our own hardware, and the hub already answers the
              route that turn calls. Each hop below carries its own status, because three of the
              four run today and the fourth does not.
            </p>
            <Wiring />
            <a className="f-link" href={`${base}/use-cases/`}>
              See the whole loop as one product — the multi-site operator →
            </a>
          </div>
        </section>

        {/* ---------------- domains ---------------- */}
        <section id="domains">
          <div className="wrap">
            <p className="eyebrow">Domains</p>
            <h2 className="h">A domain arrives as data. The runtime never changes.</h2>
            <p className="lede">
              Six operators are closed over one record — <code>step</code>, <code>observe</code>,{" "}
              <code>check</code>, <code>rollout</code>, <code>diff</code>, <code>traceHash</code>.
              Adding a domain adds a record. Adding a capability adds an operator, and there are six
              of those. That asymmetry is what separates a simulation runtime from a pile of bespoke
              simulators.
            </p>

            <div className="tblwrap scrollx">
              <table>
                <caption>
                  <b>ONTOLOGY</b> — the five slots, and who is allowed to compute each one
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Slot</th>
                    <th scope="col">Supplies</th>
                    <th scope="col">Who computes it</th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">state</th>
                    <td className="v">typed fields, units mandatory</td>
                    <td>schema</td>
                  </tr>
                  <tr>
                    <th scope="row">actions</th>
                    <td className="v">name, actor, params</td>
                    <td>schema</td>
                  </tr>
                  <tr className="is-chosen">
                    <th scope="row">transition</th>
                    <td className="v">how an action changes the state</td>
                    <td>code, never a model</td>
                  </tr>
                  <tr className="is-chosen">
                    <th scope="row">invariants</th>
                    <td className="v">what must always hold</td>
                    <td>code, never a model</td>
                  </tr>
                  <tr>
                    <th scope="row">initial</th>
                    <td className="v">where it starts</td>
                    <td>data</td>
                  </tr>
                </tbody>
              </table>
            </div>

            <div className="grid3" style={{ gridTemplateColumns: "1fr 1fr" }}>
              <div className="cell">
                <p className="k">Domain 01 — storefront</p>
                <h3>A WhatsApp storefront under a sales agent</h3>
                <p className="t">
                  Stock and money conserve. The demo runs it ungoverned, catches it overselling
                  inventory it does not have, forks the history at the moment before the damage and
                  replays with a governor installed.
                </p>
              </div>
              <div className="cell">
                <p className="k">Domain 02 — clinic</p>
                <h3>An appointment desk, and the generality proof</h3>
                <p className="t">
                  Its own transition, its own conservation law, its own fourteen tests. It is the
                  answer to &ldquo;does this only work for your toy storefront?&rdquo; — the runtime
                  did not change to accept it.
                </p>
              </div>
            </div>
          </div>
        </section>

        {/* ---------------- use cases ---------------- */}
        <section id="uses">
          <div className="wrap">
            <p className="eyebrow">Where it fits</p>
            <h2 className="h">Bring one context and one thing that must never be true.</h2>
            <p className="lede">
              An ontology is a record, not a codebase: what the state is, what actions exist, how an
              event folds into the state, and what must always hold. Two of those four are code and
              always will be.
            </p>
            <div className="uses">
              {USES.map((u) => (
                <div className="use" key={u.n}>
                  <p className="n">{u.n}</p>
                  <h3>{u.h}</h3>
                  <p>{u.p}</p>
                  <span className="ask">{u.ask}</span>
                </div>
              ))}
            </div>
            <a className="f-link" href={`${base}/use-cases/`}>
              The one we have worked out in full: an operating twin for a multi-site business →
            </a>
          </div>
        </section>

        {/* ---------------- build state ---------------- */}
        <section id="state">
          <div className="wrap">
            <p className="eyebrow">Build state</p>
            <h2 className="h">What runs, what does not, and what is unmeasured.</h2>
            <p className="lede">
              Every figure on this page is printed by a command in the Parallax runtime at seed 42
              over a horizon of 12 steps. There are no customer deployments, no accuracy claims and no
              benchmark numbers here, because we have none.
            </p>
            <div className="state2">
              <div>
                <h3 className="mlab">Runs today</h3>
                <ul className="runs">
                  <li>The runtime and its six operators</li>
                  <li>Append-only log with copy-on-write forking</li>
                  <li>The reproducibility lattice, and the policy certifier that enforces it</li>
                  <li>Conservation and safety invariant checking</li>
                  <li>The accept gate, brand-checked at runtime</li>
                  <li>The conversation layer as pure functions</li>
                  <li>The self-contained run receipt</li>
                  <li>A CLI, an HTTP hub and a tool surface over the same handlers</li>
                  <li>A second domain — the clinic, the generality proof</li>
                </ul>
              </div>
              <div>
                <h3 className="mlab">Designed, not built</h3>
                <ul className="plan">
                  <li>The LLM adapter — today&rsquo;s actors are seeded and pure</li>
                  <li>A third domain, and a domain supplied by someone who is not us</li>
                  <li>The web console</li>
                  <li>
                    A live WhatsApp number; the channel layer is pure functions with no transport
                    attached
                  </li>
                </ul>
              </div>
              <div>
                <h3 className="mlab">Not measured</h3>
                <ul className="none">
                  <li>Nothing here is calibrated against a real business</li>
                  <li>No accuracy percentage, because we cannot support one</li>
                  <li>No customer results, because there are no customers</li>
                </ul>
              </div>
            </div>
            <Verdict>
              We would rather say that than publish an accuracy number we cannot support. It is the
              oldest open item in this project and it cannot be closed by writing code.
            </Verdict>
          </div>
        </section>

        {/* ---------------- objections ---------------- */}
        <section id="objections">
          <div className="wrap">
            <p className="eyebrow">Objections</p>
            <h2 className="h">Reasonable things to distrust about this.</h2>
            <div className="qa">
              <div>
                <p className="q">It is still a simulation. Why would I trust the number?</p>
                <p className="a">
                  Do not trust the number. Check what it says about itself. This run reports 0 of 12
                  steps observed in its own receipt, unprompted, and its policy&rsquo;s declared
                  class was measured against a repeated probe instead of believed. Nothing here is
                  calibrated against a real business, and there is no accuracy figure on this page
                  because we cannot support one.
                </p>
              </div>
              <div>
                <p className="q">Is a language model computing my numbers?</p>
                <p className="a">
                  No. The transition function and the invariants are code — <code>activate</code>{" "}
                  refuses an ontology that supplies neither. A model&rsquo;s only job is reading a
                  mess into typed observations, and nothing downstream of that projection is a
                  model&rsquo;s opinion. Today the actors are seeded and pure.
                </p>
              </div>
              <div>
                <p className="q">What if the proposed ontology is wrong for my business?</p>
                <p className="a">
                  Then you answer the questions differently, or reject it, and nothing activates
                  while a blocking question is open. What you cannot do today is accept part of it:
                  acceptance is all-or-nothing plus the set of answered slots. Editing a proposal
                  produces a new proposal with a new hash, which is the honest behaviour and also
                  the more annoying one.
                </p>
              </div>
              <div>
                <p className="q">We already A/B test.</p>
                <p className="a">
                  A/B testing spends real customers and real weeks, and it cannot evaluate a
                  decision you only make once. A fork is a branch record. The two compose: use this
                  to decide what is worth testing for real.
                </p>
              </div>
              <div>
                <p className="q">Our context is a mess.</p>
                <p className="a">
                  Then the proposal comes back smaller and emptier. The one it made of the
                  Parallax project directory proposed zero invariants and seven blocking questions,
                  and said so in the message rather than filling the gaps with something plausible.
                  An empty slot is information about your context, not a failure of the tool.
                </p>
              </div>
            </div>
            <a className="f-link" href={proof("")}>
              Read the full proof page — tables, receipts and verbatim output →
            </a>
          </div>
        </section>

        {/* ---------------- close ---------------- */}
        <section id="start" className="band">
          <div className="wrap">
            <div className="col">
              <p className="eyebrow">Start</p>
              <h2 className="h">Reproduce every number on this page.</h2>
              <p className="lede">
                Requires Bun. The demo runs a WhatsApp storefront under an ungoverned sales agent,
                catches it overselling, forks the history at the moment before the damage, replays
                the same twelve steps with a governor installed, and prints the difference.
              </p>
              <pre>
                <code>
                  {"$ git clone "}
                  {CLONE}
                  {"\n$ cd skills/"}
                  {RUNTIME}
                  {"\n"}
                  {"$ bun install\n"}
                  {"$ "}
                  <b>bun run demo</b>
                  {"           "}
                  <span className="c"># run, observe, check, fork, prove</span>
                  {"\n$ "}
                  <b>bun run demo:whatsapp</b>
                  {"  "}
                  <span className="c"># the same thing as one thread, ending in a receipt</span>
                  {"\n$ "}
                  <b>bun run demo:live</b>
                  {"      "}
                  <span className="c"># the same thread against the deployed hub</span>
                  {"\n$ "}
                  <b>bun run mutants</b>
                  {"        "}
                  <span className="c"># deletes a guarantee, checks whether anything goes red</span>
                </code>
              </pre>
              <div className="actions">
                <a className="cta" href={REPO} rel="noopener">
                  Read the source
                </a>
                <a className="cta ghost" href={`${HUB}/health`} rel="noopener">
                  Check the running commit
                </a>
              </div>
            </div>
          </div>
        </section>

        <footer>
          <div className="fwrap">
            <div className="fcols">
              <div>
                <h2>Product</h2>
                <ul>
                  <li>
                    <a href="#guarantees">Guarantees</a>
                  </li>
                  <li>
                    <a href="#how">How it works</a>
                  </li>
                  <li>
                    <a href="#domains">Domains</a>
                  </li>
                  <li>
                    <a href="#uses">Where it fits</a>
                  </li>
                  <li>
                    <a href={`${base}/use-cases/`}>Multi-site operator</a>
                  </li>
                </ul>
              </div>
              <div>
                <h2>Build</h2>
                <ul>
                  <li>
                    <a href="#surface">CLI, HTTP and tools</a>
                  </li>
                  <li>
                    <a href="#channel">WhatsApp and Kapso</a>
                  </li>
                  <li>
                    <a href={`${HUB}/health`} rel="noopener">
                      Hub health
                    </a>
                  </li>
                  <li>
                    <a href={`${REPO}/README.md#run-it`} rel="noopener">
                      Run it locally
                    </a>
                  </li>
                </ul>
              </div>
              <div>
                <h2>Evidence</h2>
                <ul>
                  <li>
                    <a href={proof("")}>The proof page</a>
                  </li>
                  <li>
                    <a href="#state">Build state</a>
                  </li>
                  <li>
                    <a href="#objections">Objections</a>
                  </li>
                </ul>
              </div>
              <div>
                <h2>Project</h2>
                <ul>
                  <li>
                    <a href={REPO} rel="noopener">
                      GitHub
                    </a>
                  </li>
                  <li>
                    <a href={`${CLONE}/blob/main/${RUNTIME}/LICENSE`} rel="noopener">
                      Apache-2.0
                    </a>
                  </li>
                </ul>
              </div>
            </div>
            OPERATORS step · observe · check · rollout · diff · trace
            <br />
            CLASSES PINNED · STABLE · RECORDED &nbsp;·&nbsp; ORIGINS observed · simulated
            <br />
            <a href={REPO} rel="noopener">
              github.com/broomva/skills
            </a>{" "}
            · Apache-2.0 · Carlos Escobar (@broomva)
            <p className="note">
              Every number on this page is printed by <code>bun run demo</code> or{" "}
              <code>bun run demo:whatsapp</code> in the runtime, at seed 42 over a horizon of 12
              steps, and every quoted string is copied from that output or from the source file
              named beside it. There are no customer deployments, no accuracy claims and no
              benchmark results, because we have none — and inventing them is the exact failure this
              system exists to make visible.
            </p>
          </div>
        </footer>
      </main>
    </>
  );
}
