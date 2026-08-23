import type { Metadata } from "next";
import { AsciiField } from "../../components/AsciiField";
import { AutoScroll } from "../../components/AutoScroll";
import { DemoCinema, type Scene } from "../../components/DemoCinema";
import { MotionPanel } from "../../components/MotionPanel";
import { REPO } from "../../lib/repo";
import type { MotionId } from "../../remotion/registry";
import "./demo.css";

const base = process.env.NEXT_PUBLIC_BASE_PATH ?? "";
const HUB = "https://parallax-hub.onrender.com";

export const metadata: Metadata = {
  title: "Parallax — la decisión que no tomaste",
  description:
    "Un gemelo operativo para negocios multi-sede: propone un modelo de tu operación desde lo que ya existe, espera a que lo aceptes, y sólo entonces simula la decisión que estás considerando. Cada número dice cuánto de él fue real.",
};

/**
 * Six shots, five clips. The prose is the argument and the footage is the room
 * it happens in — so the copy here is not a caption for the film, it stands on
 * its own, and the film is legible with the sound of it off.
 */
const SCENES: Scene[] = [
  {
    id: "servicio",
    title: "Un negocio real, un viernes cualquiera.",
    body: "Varias sedes, inventario que se mueve, turnos que alguien acomodó de memoria. Casi nada de esto vive en un sistema: vive en WhatsApp, en el POS y en la cabeza del que lleva años ahí.",
    alt: "The pass of a small restaurant kitchen at dusk, two cooks working, crates of produce stacked in the foreground, warm lamps against cold window light.",
  },
  {
    id: "cierre",
    title: "Toda decisión operativa se toma una sola vez.",
    body: "Cambias un precio, un turno, un pedido. El mundo se mueve — y la alternativa nunca se observa. No existe un ambiente de pruebas para la forma en que opera un negocio.",
    alt: "The same kitchen after closing, empty and still, a single overhead lamp left on above the steel counter.",
  },
  {
    id: "gemelo",
    title: "Parallax reconstruye el negocio desde lo que ya hay.",
    body: "Le apuntas a un contexto — tus datos, el espacio de trabajo de un agente, o una carpeta cualquiera — y propone un modelo: qué cosas existen, qué acciones son posibles, qué no puede dejar de ser cierto nunca.",
    alt: "The same kitchen rendered as a luminous wireframe, surfaces reduced to glowing pale edges suspended in dark space.",
  },
  {
    id: "compuerta",
    title: "Nada corre hasta que lo aceptas.",
    body: "Un modelo que nadie revisó no debería poder producir números que se ven autoritativos. Si falta una unidad en una cantidad, se niega a activarse. Falla cerrado — no adivina.",
    alt: "The luminous model held behind a single vertical plane of pale light crossing the frame, the geometry beyond it dimmed and paused.",
  },
  {
    id: "bifurcacion",
    title: "Bifurcas la historia y cambias exactamente una cosa.",
    body: "Mismo estado inicial, misma semilla, una política distinta. El log es append-only, así que una rama no cuesta nada. El ángulo entre las dos ramas es la medición — eso significa la palabra parallax.",
    alt: "Two translucent copies of the same luminous kitchen drifting apart, one dense and hot, one calm and cool, a widening gap between them.",
  },
  {
    id: "regreso",
    title: "Y cada número dice cuánto de él fue real.",
    body: "Tipado observado o simulado desde que nace, y la marca se propaga: un valor derivado de algo simulado es simulado, por mucho dato real que haya entrado al lado.",
    alt: "The real kitchen again the following evening, warm and unhurried, one cook plating calmly, shelves neatly stocked.",
  },
];

// Five clips, six posters. The N+1 is the mechanism, not a convention: clip i
// runs from poster i to poster i+1, so every seam is a crossfade between frames
// that converge, and the posters alone are the whole reduced-motion experience.
// webp because that is what the pipeline emits and what the budget gate
// measured -- the .jpg stills beside them are generation intermediates.
const CLIPS = [1, 2, 3, 4, 5].map((n) => `${base}/cinema/0${n}.mp4`);
const POSTERS = [1, 2, 3, 4, 5, 6].map((n) => `${base}/cinema/0${n}.webp`);

/** Each panel is a guarantee the runtime enforces, not a feature it offers. */
const GUARANTEES: Array<{
  id: MotionId;
  n: string;
  kicker: string;
  title: string;
  body: string;
  proof: string;
}> = [
  {
    id: "AcceptGate",
    n: "01",
    kicker: "La compuerta",
    title: "Una ontología que nadie aceptó no puede correr.",
    body: "La compuerta es una verificación en tiempo de ejecución, no una convención del sistema de tipos. Se niega mientras haya una pregunta bloqueante abierta, y una unidad en una cantidad numérica siempre bloquea.",
    proof: "activate() → BLOCKING_QUESTIONS_OPEN",
  },
  {
    id: "ForkDiverge",
    n: "02",
    kicker: "La bifurcación",
    title: "Misma historia, una decisión distinta.",
    body: "Bajo un agente de ventas sin gobernador, la tienda promete inventario que no tiene. Bifurcada en el paso anterior al daño, con el gobernador puesto, los mismos doce pasos producen cero.",
    proof: "9 violaciones → 0, seed 42, horizonte 12",
  },
  {
    id: "Provenance",
    n: "03",
    kicker: "El tipado",
    title: "Ningún número sale sin decir cuánto de él fue real.",
    body: "Cada valor nace tipado observado o simulado, y la derivación une las marcas. Una entrada simulada hace simulada la respuesta, hasta la última línea. Por eso una cifra de Parallax no se puede citar como medición por accidente.",
    proof: "observed | simulated, y la marca se propaga",
  },
  {
    id: "ReplayHash",
    n: "04",
    kicker: "La prueba",
    title: "Una política no puede certificar su propia reproducibilidad.",
    body: "El determinismo se verifica en cinco segundos, así que lo verificamos en vez de afirmarlo. Una política que no logra reproducir su propio resultado con la misma semilla queda degradada sin importar lo que declare — y la degradación se escribe en la rama.",
    proof: "misma semilla → mismo hash · actor sin fijar → PINNED baja a STABLE",
  },
];

export default function Demo() {
  return (
    <main className="demo">
      <a className="skip" href="#reduccion">
        Saltar la secuencia de apertura
      </a>

      {/* A hands-free three-minute pass through the page; the reader can take
          over at any point. */}
      <AutoScroll totalSeconds={180} />

      <DemoCinema scenes={SCENES} clips={CLIPS} posters={POSTERS} />

      {/* ---------------- the reduction ----------------
          The same frame the film opens on, run through a text rasterizer. It
          earns its place by being the argument rather than decorating it: a
          representation is lossy on purpose, and the useful question about one
          is never whether it is pretty but whether you can see what it dropped. */}
      <section className="act band" id="reduccion">
        <div className="wrap">
          <AsciiField
            alt="The opening frame of the film — a working kitchen — redrawn out of typographic characters and held still, because it already happened. Over it, a solid recorded line runs in from the left, reaches a fork, and opens into nine candidate trajectories that extend, brighten, and then collapse as exactly one of them is taken."
            src={`${base}/cinema/01.webp`}
          />
          <p className="band-cap">
            <b>Un modelo es una pérdida deliberada de información.</b> El fondo quieto es el cuadro
            con el que abre la película, redibujado con caracteres: se reconoce la cocina, y se ve
            exactamente qué se perdió. Lo único que se mueve son las trayectorias, porque son lo
            único que todavía no pasó — un solo pasado observado, muchos futuros simulados, y al
            final se toma uno. <b>Los demás nunca se observan.</b> Ésos son los que Parallax te deja
            mirar antes de elegir.
          </p>
        </div>
      </section>

      {/* ---------------- the thesis ---------------- */}
      <section className="act" id="tesis">
        <div className="wrap">
          <p className="eyebrow">La tesis</p>
          <h2 className="act-h">
            Las pymes no carecen de datos. Carecen de una representación operativa coherente del
            negocio.
          </h2>
          <p className="act-l">
            Sus datos están fragmentados y muchas de sus decisiones viven en conversaciones. Lo
            difícil de un gemelo operativo no es pronosticar: es construir un modelo del negocio que
            alguien pueda revisar antes de creerle. Eso es lo que corre hoy.
          </p>
          <ol className="loop">
            {[
              ["Observar", "datos del negocio, workspace de un agente, o una carpeta cualquiera"],
              ["Estructurar", "una ontología propuesta desde lo que realmente hay ahí"],
              ["Aceptar", "un humano responde las preguntas bloqueantes y acepta"],
              ["Simular", "bifurcar el log y cambiar exactamente una decisión"],
              ["Recomendar", "una acción concreta en el canal donde el negocio ya opera"],
              ["Medir", "lo que pasó de verdad: simulado se vuelve observado"],
            ].map(([k, t], i) => (
              <li className={i === 2 ? "gate" : undefined} key={k}>
                <span className="loop-n">{String(i + 1).padStart(2, "0")}</span>
                <span className="loop-k">{k}</span>
                <span className="loop-t">{t}</span>
              </li>
            ))}
          </ol>
          <p className="act-note">
            El tercer paso no es un trámite. Es el producto — y es el único de los seis que la
            mayoría de los simuladores no tiene.
          </p>
        </div>
      </section>

      {/* ---------------- the guarantees ---------------- */}
      <section className="act dark" id="garantias">
        <div className="wrap wide">
          <p className="eyebrow">Lo que se exige en código</p>
          <h2 className="act-h">
            Cuatro garantías, cada una una verificación en tiempo de ejecución.
          </h2>
          <p className="act-l">
            Un simulador produce números seguros sobre un mundo que no existe, y casi nunca te da
            cómo verificarlos. La respuesta habitual es prometer más fidelidad, que no se puede
            comprobar desde afuera. Estas cuatro sí.
          </p>

          <div className="glist">
            {GUARANTEES.map((g, i) => (
              <article className={`gcard${i % 2 === 1 ? " flip" : ""}`} key={g.id}>
                <div className="gcopy">
                  <p className="eyebrow">
                    {g.n} · {g.kicker}
                  </p>
                  <h3 className="gt">{g.title}</h3>
                  <p className="gb">{g.body}</p>
                  <p className="gp">{g.proof}</p>
                </div>
                <div className="gmedia">
                  <MotionPanel alt={g.title} id={g.id} />
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      {/* ---------------- honest status ---------------- */}
      <section className="act" id="estado">
        <div className="wrap">
          <p className="eyebrow">Estado honesto</p>
          <h2 className="act-h">Lo que corre, y lo que no.</h2>
          <div className="grid2">
            <div className="cell built">
              <p className="k">Existe y corre</p>
              <ul>
                <li>El runtime y sus seis operadores</li>
                <li>El log con bifurcación copy-on-write</li>
                <li>La retícula de reproducibilidad</li>
                <li>El verificador de invariantes de conservación</li>
                <li>La propuesta de ontología y su compuerta</li>
                <li>CLI, hub HTTP y superficie de herramientas para agentes</li>
                <li>
                  Un segundo dominio — un consultorio, con su propia transición y su propia ley de
                  conservación. <b>El runtime no cambió para aceptarlo.</b>
                </li>
              </ul>
            </div>
            <div className="cell unbuilt">
              <p className="k">Diseñado y no construido</p>
              <ul>
                <li>El adaptador de LLM — hoy los actores son semilla pura</li>
                <li>Un tercer dominio</li>
                <li>Un dominio aportado por alguien que no seamos nosotros</li>
                <li>La consola web</li>
                <li>El brazo de adquisición: que la demanda que entra alimente el mismo modelo</li>
              </ul>
              <p className="warn">
                Nada aquí está calibrado contra un negocio real, porque todavía no tenemos
                transcripciones reales. Preferimos decirlo a publicar un porcentaje de precisión que
                no podemos sustentar.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ---------------- the close ---------------- */}
      <section className="act close" id="cierre">
        <div className="wrap">
          <p className="line">
            La meta nunca fue un simulador que acierte.
            <br />
            Es <b>un simulador que no puede mentir sobre ser un simulador.</b>
          </p>
          <div className="actions">
            <a className="cta" href={REPO} rel="noopener">
              Leer el código
            </a>
            <a className="cta ghost" href={`${base}/proof/`}>
              La página de evidencia
            </a>
            <a className="cta ghost" href={`${base}/`}>
              El producto
            </a>
          </div>
          <p className="foot">
            El hub responde en <code>{HUB}</code> — <code>GET /health</code> reporta el commit que
            está corriendo, que es el único campo de esa respuesta que una imagen vieja no puede
            falsificar. Carlos Escobar (@broomva) · Apache-2.0.
          </p>
        </div>
      </section>
    </main>
  );
}
