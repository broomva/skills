import type { Metadata } from "next";
import { MotionPanel } from "../../components/MotionPanel";
import { Nav } from "../../components/Nav";
import { Verdict } from "../../components/Verdict";
import { Wiring } from "../../components/Wiring";
import { REPO } from "../../lib/repo";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";

export const metadata: Metadata = {
  title: "Parallax — an operating twin for multi-site businesses",
  description:
    "A worked use case: turning POS, WhatsApp and scattered files into a living model of a business that anticipates, simulates and recommends — built on the Parallax runtime.",
};

/**
 * observar → estructurar → predecir → simular → recomendar → medir → recalibrar
 *
 * The claim the page has to earn is that this is not seven new subsystems. It
 * is the six operators plus the accept gate, arranged in a circle. The table
 * below is where that is either true or it is marketing, so every row names
 * the thing in the runtime that does the work.
 */
const LOOP = [
  {
    sp: "observar",
    op: "intake",
    t: "POS exports, WhatsApp threads, spreadsheets, the folder someone keeps the recipes in. No integration agreed in advance and no schema to fill in first.",
  },
  {
    sp: "estructurar",
    op: "proposeOntology + accept",
    t: "Sites, staff, inventory, shifts, suppliers, sales — proposed from what was actually in the sources, with the questions it could not answer left open. The operator accepts it before anything forecasts.",
  },
  {
    sp: "predecir",
    op: "rollout",
    t: "A forecast expressed over real entities rather than an anonymous series: this site, this Friday, this shift. Typed simulated, because it has not happened.",
  },
  {
    sp: "simular",
    op: "fork + diff",
    t: "Do nothing, against the action being considered. Same state, same seed, one decision different. The gap between the two branches is the argument for acting.",
  },
  {
    sp: "recomendar",
    op: "conversation + receipt",
    t: "One concrete action in the channel the business already uses, with the receipt behind it rather than a chart in place of it.",
  },
  {
    sp: "medir",
    op: "observe",
    t: "What actually happened. The quantity does not change its name, it changes its type: simulated becomes observed, and the receipt's split moves.",
  },
  {
    sp: "recalibrar",
    op: "certifyPolicy",
    t: "Forecast against outcome, written into the record. A policy that stops reproducing gets demoted whatever it declares about itself.",
  },
];

const LAYERS: Array<[string, string]> = [
  ["Product", "A predictive operating copilot, WhatsApp-first"],
  ["First user", "The owner or operator of a business with several sites"],
  ["First strong case", "Staffing, inventory and demand in restaurants and franchises"],
  ["Interface", "Alerts, questions, approvals, charts and reports over WhatsApp"],
  ["Engine", "Context assembly, code, statistical models, simulation, agents"],
  ["Representation", "A dynamic ontology — SQL, files or a graph, decided by the context"],
  ["Moat", "A calibrated history of prediction → decision → outcome"],
];

export default function UseCases() {
  return (
    <main className="after" id="main">
      <Nav base={base} />

      <section className="hero">
        <div className="wrap">
          <div className="badges">
            <span className="badge">Use case</span>
            <span className="badge">Multi-site operations</span>
            <span className="badge">Proposal, not a deployment</span>
          </div>
          <h1 className="h1">
            Your business tells you what is about to happen, and helps you act first.
          </h1>
          <p className="sub">
            An AI operator for multi-site businesses that turns POS, WhatsApp and scattered files
            into a living model of the business — anticipating problems, simulating alternatives and
            coordinating action before money is lost.
          </p>
          <Verdict>
            Nothing on this page is running for a customer. What exists is the runtime underneath
            it: the ontology proposal and its accept gate, the forkable log, the conservation
            checker, the receipt and the reproducibility lattice. This page is the argument that
            those are the right primitives for this product, and it says which parts are still
            missing.
          </Verdict>
        </div>
      </section>

      <section id="thesis">
        <div className="wrap">
          <p className="eyebrow">The thesis</p>
          <h2 className="h">
            Small businesses do not lack data. They lack a coherent operational model of themselves.
          </h2>
          <p className="lede">
            The data is fragmented across a point-of-sale system, a set of spreadsheets and a phone,
            and a large share of the decisions live in conversations that were never written down
            anywhere. This is not a reporting problem, and a dashboard does not touch it.
          </p>
          <p className="lede" style={{ marginTop: 16 }}>
            What is missing is a representation: a model of how this business actually runs,
            assembled from the traces it already produces, kept current, and usable for asking what
            happens if. That is the thing Parallax proposes, gates behind a human, and then rolls
            forward.
          </p>

          <blockquote className="quote">
            &ldquo;La búsqueda es generalizable, y lo que retorna el agente tiene que razonar cómo
            articularlo en la ontología según el modelo de datos que va emergiendo.&rdquo;
            <cite>the line the whole design follows from</cite>
          </blockquote>

          <p className="body" style={{ marginTop: 24 }}>
            The consequence is the interesting part, and it is the opposite of how these systems are
            usually built. The ontology is not installed first. It is discovered and corrected by
            watching the business, so search is a way of reconstructing context rather than the
            product, and predictions are expressed over real entities — this site, this employee,
            this supplier — rather than over an anonymous time series. Actions and their outcomes
            then feed the model that produced them.
          </p>
        </div>
      </section>

      <section id="loop">
        <div className="wrap wide">
          <p className="eyebrow">The loop</p>
          <h2 className="h">Seven stations, and not one of them is a new subsystem.</h2>
          <p className="lede">
            observar → estructurar → predecir → simular → recomendar → medir → recalibrar. Each
            station below names the operator in the runtime that does the work, because a loop drawn
            over primitives that do not exist is a diagram, not an architecture.
          </p>

          <div style={{ marginTop: 40 }} className="loopwrap">
            <MotionPanel
              id="OperatorLoop"
              className="loop"
              alt="A seven-station track: observar, estructurar, predecir, simular, recomendar, medir, recalibrar. A token travels through them. At observar, three sources arrive: POS, WhatsApp and spreadsheets. At estructurar a proposed ontology of sites, staff, inventory, shifts and suppliers is accepted by the operator. At predecir a forecast of plus twenty-two percent at one site is drawn, tagged simulated. At simular two branches are compared: doing nothing runs short of two ingredients and short-staffed between seven and nine, while moving one employee and ordering eighteen extra kilos leaves zero shortfalls. At recomendar the recommendation is delivered as a WhatsApp message ending in a question and a receipt link. At medir the real outcome, plus nineteen percent with zero shortfalls, arrives tagged observed. At recalibrar the three-point forecast error is written into the record, and a dotted arc returns from the last station to the first."
            />
          </div>

          <ol className="loopgrid">
            {LOOP.map((s) => (
              <li key={s.sp}>
                <p className="sp">{s.sp}</p>
                <p className="op">{s.op}</p>
                <p className="t">{s.t}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="example">
        <div className="wrap">
          <p className="eyebrow">Worked example</p>
          <h2 className="h">What the operator actually receives.</h2>
          <p className="lede">
            The regression, the chart and the explanation can all be attached. They are evidence for
            the recommendation; they are not the product. The product is one message that names a
            decision and can be answered with a word.
          </p>

          <div className="thread">
            <div className="msg bot">
              <p className="who">Parallax · Thursday 18:40</p>
              <div className="bub">
                <pre>{`La sede de Chapinero probablemente venderá 22% más este viernes.

Si no haces nada, faltarán dos insumos y habrá déficit de
personal entre 7 y 9 p.m.

Recomiendo mover a Cindy, ordenar 18 kg adicionales y adelantar
el pedido.

¿Lo ejecuto?`}</pre>
              </div>
            </div>
            <div className="msg them">
              <p className="who">Operator</p>
              <div className="bub">
                <pre>Sí, pero deja el pedido para mañana temprano</pre>
              </div>
            </div>
            <div className="msg bot">
              <p className="who">Parallax</p>
              <div className="bub">
                <pre>{`Hecho. Turno actualizado, pedido programado 6:00 a.m.

Pronóstico +22% · simulado · clase PINNED
Recibo completo: /r/bef312a9`}</pre>
              </div>
            </div>
            <div className="msg bot">
              <p className="who">Parallax · Saturday 09:10</p>
              <div className="bub">
                <pre>{`Viernes cerrado: +19% real, 0 faltantes, turno cubierto.

Pronóstico 22% → real 19%. Error de 3 puntos, registrado.`}</pre>
              </div>
            </div>
          </div>

          <Verdict>
            The last message is the one that matters and it is the one this kind of product usually
            skips. A recommendation nobody scored is a guess with good manners.
          </Verdict>
        </div>
      </section>

      <section id="layers">
        <div className="wrap">
          <p className="eyebrow">Product, technology, moat</p>
          <h2 className="h">Three different things, kept apart on purpose.</h2>
          <div className="tblwrap scrollx">
            <table>
              <caption>
                <b>LAYERS</b> — the product is not the engine, and neither is the defensibility
              </caption>
              <thead>
                <tr>
                  <th scope="col">Layer</th>
                  <th scope="col">What it is</th>
                </tr>
              </thead>
              <tbody>
                {LAYERS.map(([k, v]) => (
                  <tr key={k} className={k === "Moat" ? "is-chosen" : undefined}>
                    <th scope="row">{k}</th>
                    <td className="v">{v}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="body" style={{ marginTop: 24 }}>
            The moat row is the only one that cannot be bought or copied in a quarter, and it is the
            one Parallax is built to produce. A receipt binds a forecast to the decision it caused
            and to the outcome that followed, under a seed that makes the whole thing replayable. A
            year of those is a calibrated record of this specific business. A year of chat logs is
            not.
          </p>
        </div>
      </section>

      <section id="wiring">
        <div className="wrap">
          <p className="eyebrow">How it is wired</p>
          <h2 className="h">WhatsApp, Kapso, Genesis, and the hub.</h2>
          <p className="lede">
            The channel is not a metaphor. A real WhatsApp message already runs an agent turn in a
            confined workspace on our own hardware, and the hub already answers the route that turn
            would call. Here is each hop and whether it carries traffic today.
          </p>
          <Wiring />

          <h3 className="mlab" style={{ marginTop: 48 }}>
            What is still missing for this use case
          </h3>
          <div className="state2">
            <div>
              <h3 className="mlab">Exists</h3>
              <ul className="runs">
                <li>The ontology proposal and its accept gate</li>
                <li>Append-only log with copy-on-write forking</li>
                <li>Conservation invariants, checked in code</li>
                <li>The receipt, with its own observed/simulated split</li>
                <li>The reproducibility lattice and the policy certifier</li>
                <li>A live WhatsApp → agent path on our own VPS</li>
              </ul>
            </div>
            <div>
              <h3 className="mlab">Needed next</h3>
              <ul className="plan">
                <li>A POS intake alongside the filesystem and table proposers</li>
                <li>A forecasting actor — today&rsquo;s actors are seeded and pure</li>
                <li>
                  A restaurant domain: its transition, and the conservation law it already keeps
                </li>
                <li>Joining the Genesis session to the hub for a real number</li>
                <li>The write-back that turns an approval into an action</li>
              </ul>
            </div>
            <div>
              <h3 className="mlab">Unmeasured</h3>
              <ul className="none">
                <li>No forecast has been scored against a real Friday</li>
                <li>No business has been modelled from its own transcripts</li>
                <li>The +22% and the +19% above are illustration, not results</li>
              </ul>
            </div>
          </div>
          <Verdict>
            The third column is the one to read first. The numbers in the example thread are made up
            to show the shape of the message, and a system whose whole claim is that a number must
            say how much of it was real does not get to be vague about that on its own website.
          </Verdict>
        </div>
      </section>

      <section id="start" className="band">
        <div className="wrap">
          <div className="col">
            <p className="eyebrow">Start</p>
            <h2 className="h">The runtime is the part that already works.</h2>
            <p className="lede">
              Point it at a directory and it will propose a model of it, refuse to run until you
              accept, and hand you a receipt that says what share of its own answer was real.
            </p>
            <div className="actions">
              <a className="cta" href={REPO} rel="noopener">
                Read the source
              </a>
              <a className="cta ghost" href={`${base}/`}>
                Back to the product
              </a>
            </div>
          </div>
        </div>
      </section>

      <footer>
        <div className="fwrap">
          Parallax · point it at a context · accept the ontology · fork it · prove it
          <br />
          <a href={REPO} rel="noopener">
            github.com/broomva/skills
          </a>{" "}
          · Apache-2.0 · Carlos Escobar (@broomva)
          <p className="note">
            This page describes a product that is proposed and a runtime that is built. Where the
            two are confused, the runtime is the one with tests and the product is the one without
            customers.
          </p>
        </div>
      </footer>
    </main>
  );
}
