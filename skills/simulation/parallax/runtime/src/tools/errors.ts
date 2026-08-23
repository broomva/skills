/**
 * The error vocabulary of the agent-facing surface.
 *
 * Nothing here is new machinery: it re-exports `src/core/result.ts` unchanged so
 * that a tool call, a CLI invocation and an HTTP response all carry the SAME
 * value shape `{code, reason, detail?}` with the SAME codes. That identity IS
 * the "the agent is a user, not a client library" claim. A transport that
 * invents its own error words has quietly become the client library.
 *
 * Codes are listed here so a caller can exhaustively switch on them without
 * reading five modules. Library codes (SOURCE_UNREADABLE, BLOCKING_QUESTIONS_OPEN,
 * POLICY_THREW, ...) propagate UNCHANGED from src/core -- they are not
 * re-wrapped, re-worded, or renamed on the way out.
 */

export { err, fail, isOk, ok, type ParallaxError, type Result } from "../core/result";

/** Codes the tool layer adds. Everything else is propagated from src/core. */
export type ToolErrorCode =
  // containment -- a path this surface refused to follow
  | "PATH_ABSOLUTE"
  | "PATH_ESCAPES_WORKSPACE"
  | "PATH_NOT_FOUND"
  | "WORKSPACE_UNREADABLE"
  | "ROOT_NOT_ALLOWED"
  | "WORKSPACE_DENIED"
  | "WORKSPACE_NOT_WRITABLE"
  | "TABLES_REQUIRED"
  // pending-proposal addressing
  | "NO_PENDING_PROPOSAL"
  | "UNKNOWN_REF"
  | "AMBIGUOUS_REF"
  | "QUESTION_OUT_OF_RANGE"
  // re-minting an acceptance in a new process
  | "WORKSPACE_MOVED"
  | "PROPOSER_CHANGED"
  | "PROPOSAL_STALE"
  | "UNKNOWN_DOMAIN"
  | "DOMAIN_CHANGED"
  | "DOMAIN_INVALID"
  | "RECONCILIATION_UNACKNOWLEDGED"
  // running
  | "NO_ACCEPTED_ONTOLOGY"
  | "UNKNOWN_ONTOLOGY"
  | "UNKNOWN_POLICY"
  | "UNKNOWN_RUN"
  // input validation, shared by every adapter
  | "INVALID_INPUT"
  // the CLI's own argument layer
  | "NO_COMMAND"
  | "UNKNOWN_COMMAND"
  | "UNKNOWN_FLAG"
  | "MISSING_FLAG"
  | "BAD_FLAG_VALUE"
  // the backstop that should never fire
  | "UNEXPECTED";

/**
 * Every code this surface can emit, including the ones it forwards from src/core.
 *
 * NOTE: this hand-mirrors core's vocabulary, and that is a known drift hazard in
 * one direction only. Adding a code in src/core breaks this file at the type
 * level, which is loud and fine -- DEGENERATE_CONTEXT and NO_ACTIONS arrived
 * that way. Removing one does NOT break anything, so a stale code can linger
 * here indistinguishable from a live one. Deriving it with a conditional type
 * was tried and does not typecheck cleanly against the re-export shape; worth
 * revisiting when there is time to change the export structure rather than
 * patch around it.
 */
export type AnyErrorCode =
  | ToolErrorCode
  | "SOURCE_UNREADABLE"
  | "SOURCE_EMPTY"
  | "UNSUPPORTED_SOURCE"
  | "DEGENERATE_CONTEXT"
  | "BLOCKING_QUESTIONS_OPEN"
  | "NO_TRANSITION"
  | "NO_INVARIANTS"
  | "NO_ACTIONS"
  | "NOT_ACCEPTED"
  | "POLICY_THREW"
  | "POLICY_EMPTY"
  | "EMPTY_TRAJECTORY"
  | "OBJECTIVE_THREW"
  | "UNANSWERED_BLOCKING"
  | "UNKNOWN_QUESTION"
  | "EMPTY_REPLY";
