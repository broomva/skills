import { Verdict } from "./Verdict";

/**
 * The transport, drawn with each hop's actual status on it.
 *
 * Three of the four hops run today and the fourth does not, and a diagram that
 * draws all four the same way is the diagram that made the README claim two
 * shipped subsystems were unbuilt. The status chip is the point of the figure.
 */

type Hop = {
  k: string;
  h: string;
  t: string;
  state: "live" | "demo" | "open";
};

const HOPS: Hop[] = [
  {
    k: "channel",
    h: "WhatsApp → Kapso",
    t: "Kapso is the Cloud API gateway. A thread id arrives as kapso:<phoneNumberId>:<waId>, and the principal is the second segment — the first is our own number and is identical on every message.",
    state: "live",
  },
  {
    k: "ingress",
    h: "Tailscale Funnel",
    t: "The webhook port is published and nothing else. SSH stays closed. AllowFunnel is keyed by host:port rather than by path, so the port is separate from the one the web app listens on.",
    state: "live",
  },
  {
    k: "runtime",
    h: "Genesis session",
    t: "One agent session per thread, in a dedicated workspace directory rather than the whole home. A fail-closed allowlist on waId: an unknown sender is refused, and the refusal is the default rather than the exception.",
    state: "live",
  },
  {
    k: "engine",
    h: "Parallax hub",
    t: "POST /api/whatsapp/turn takes {from, text, threadId} and nothing else. Every ontology, run and receipt is authored server-side, so there is no path here that hands the hub content to publish.",
    state: "demo",
  },
];

const LABEL: Record<Hop["state"], string> = {
  live: "runs in production",
  demo: "runs, driven by the demo",
  open: "designed, not built",
};

export function Wiring() {
  return (
    <>
      <ol className="hops">
        {HOPS.map((hop, i) => (
          <li key={hop.k}>
            <p className="k">
              <span className="i">{String(i + 1).padStart(2, "0")}</span>
              {hop.k}
            </p>
            <h3>{hop.h}</h3>
            <p className="t">{hop.t}</p>
            <p className={`st ${hop.state}`}>{LABEL[hop.state]}</p>
          </li>
        ))}
      </ol>
      <Verdict>
        The first three hops carry real WhatsApp traffic today. The fourth is the one that is not
        joined in production: the hub answers <code>/api/whatsapp/turn</code> and serves{" "}
        <code>/r/:id</code>, and <code>bun run demo:live</code> drives that whole thread against the
        deployed hub — but no Genesis session is calling it for a real number yet. Parallax&rsquo;s
        own channel layer is pure functions with no transport attached, which is exactly why it can
        be pointed at one.
      </Verdict>
    </>
  );
}
