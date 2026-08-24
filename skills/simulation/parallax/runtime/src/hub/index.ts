import { createHub, type Hub, type HubOptions } from "./app";

export type { Hub, HubOptions } from "./app";
export { createHub } from "./app";
export type { DomainBinding } from "./domain";
export { bindDomain, LEDGER_KEY, shieldedPolicy } from "./domain";
export type { HubState, OntologyRecord, ProposalRecord, RunRecord, ThreadRecord } from "./registry";
export type { StaticOutcome, StaticRoot } from "./static";
export { serveStatic, staticRoot } from "./static";
export { HUB_CODES, httpStatusFor, LIBRARY_CODES, STATUS_BY_CODE } from "./status";

/**
 * Bind the hub to a socket.
 *
 * Two details are host requirements rather than preferences, and both are the
 * kind that fail silently in development and loudly on deploy:
 *
 *  - The host is 0.0.0.0. A server bound to localhost is unreachable from
 *    outside its own container, and a platform that probes for an open port
 *    concludes the service never started.
 *  - PORT comes from the environment. It is 3000 only when nothing sets it;
 *    on Render it is 10000. Anything that hardcodes 3000 -- including a printed
 *    URL -- is wrong in production, so the port is read once, here, and the
 *    line this prints uses what the server actually bound.
 *
 * A malformed PORT exits rather than falling back. Falling back would bind a
 * port nobody is routing to, and the failure would surface an hour later as a
 * health check that never passes, with nothing in the log to explain it.
 */
export function startHub(options: HubOptions = {}): ReturnType<typeof Bun.serve> {
  const raw = process.env.PORT;
  const port = raw === undefined || raw.trim() === "" ? 3000 : Number(raw);
  if (!Number.isInteger(port) || port < 0 || port > 65535) {
    console.error(`PORT is not a valid port number: ${String(raw)}`);
    process.exit(1);
  }
  const hub: Hub = createHub(options);
  const server = Bun.serve({ port, hostname: "0.0.0.0", fetch: hub.fetch });
  console.log(
    `parallax hub ${hub.version} listening on http://0.0.0.0:${String(server.port)} (health: /health)`,
  );
  return server;
}

if (import.meta.main) startHub();
