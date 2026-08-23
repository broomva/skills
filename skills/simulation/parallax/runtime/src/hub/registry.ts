import type { RunReceipt } from "../artifact/receipt";
import type { ActiveOntology, OntologyProposal } from "../core/ontology";
import type { TypeRecord } from "../core/types";
import type { DomainBinding } from "./domain";

/**
 * Server-side state. All of it in memory, all of it lost when the process ends.
 *
 * WHY IT CANNOT SIMPLY BE A DATABASE
 *
 * An `ActiveOntology` is branded with a symbol that is private to
 * `src/core/ontology.ts` and checked at RUNTIME by `worldOf`. It does not
 * survive `JSON.stringify` -> `JSON.parse`, and that is deliberate: trust is
 * not a field you can copy. It has to be re-minted, by `activate`, in the
 * process that will execute it. So the ontology itself never crosses the wire.
 * Only an opaque `ontologyId` does, and the object it names lives here, in the
 * process that would run it. A client holding an id holds a reference to a
 * decision a human made inside this process -- not a token it could have
 * forged, and not a serialised claim it could have edited in transit.
 *
 * WHAT EPHEMERAL COSTS, SAID PLAINLY
 *
 * On Render's free tier there is no persistent disk, the filesystem is
 * ephemeral, and a web service is spun down after 15 minutes without traffic
 * (cold start back up takes about a minute). So: every proposal, every accepted
 * ontology, and every rendered receipt in these maps disappears on redeploy, on
 * spin-down, and on any restart the platform decides to perform. A `/r/<id>`
 * link handed to someone in the morning will 404 in the afternoon.
 *
 * That is a real limitation and it is not papered over. One thing takes the
 * edge off it and is worth knowing: the ids here are content-derived, not
 * random. Re-accepting the same proposal with the same answers under the same
 * name yields the same `ontologyId`, and re-running it with the same horizon,
 * seed and governor yields the same `runId` -- so the same URL comes back. The
 * receipt is regenerable rather than recoverable, which is the honest version
 * of persistence for a deterministic system: it is not stored, it is rebuilt
 * from the inputs that produced it.
 */

export interface ProposalRecord {
  readonly proposal: OntologyProposal;
  readonly proposedAt: number;
  /** The root actually read, absolute. Kept server-side; the wire gets a relative path. */
  readonly root: string;
}

export interface OntologyRecord {
  readonly ontologyId: string;
  readonly active: ActiveOntology;
  readonly world: TypeRecord;
  readonly binding: DomainBinding;
  readonly proposalId: string;
  readonly answers: Readonly<Record<string, string>>;
  readonly acceptedBy: string;
  readonly acceptedAt: number;
}

export interface RunRecord {
  readonly runId: string;
  readonly html: string;
  readonly receipt: RunReceipt;
  readonly at: number;
}

/** Where one WhatsApp thread stands. Keyed by threadId, never by a message id. */
export type ThreadStage = "IDLE" | "PROPOSED" | "RAN";

export interface ThreadRecord {
  stage: ThreadStage;
  /** The proposal this thread is waiting on an answer about. */
  proposalId: string | null;
  /** Answers collected so far, slot -> text. Accumulated across turns. */
  answers: Record<string, string>;
  lastRunUrl: string | null;
}

export interface HubState {
  readonly proposals: Map<string, ProposalRecord>;
  readonly ontologies: Map<string, OntologyRecord>;
  readonly runs: Map<string, RunRecord>;
  readonly threads: Map<string, ThreadRecord>;
  readonly startedAt: number;
}

export function createState(startedAt: number): HubState {
  return {
    proposals: new Map(),
    ontologies: new Map(),
    runs: new Map(),
    threads: new Map(),
    startedAt,
  };
}
