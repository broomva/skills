/**
 * The one place a typed error becomes an HTTP status.
 *
 * The hub does not invent an error vocabulary. Every failure that the library
 * can name is returned with the library's own code, unchanged, and this table
 * is the only thing the transport adds: a number HTTP clients already know how
 * to route on. That is the "agent is a user, not a client library" claim made
 * concrete -- an agent reading `{code:"BLOCKING_QUESTIONS_OPEN"}` off the wire
 * is reading the same value the in-process caller gets from `activate`.
 *
 * A second, smaller set of codes belongs to the transport itself: a body that
 * is not JSON, a route that does not exist, an id the server has never seen.
 * Those cannot come from the library because the library has no requests. They
 * are listed here explicitly rather than left to a default, so that adding one
 * is a deliberate edit to this file.
 */

/**
 * Every code the library can produce, enumerated so the test can prove each one
 * has a mapping rather than silently falling through to 500. If a new error
 * code is added to `src/core` and not added here, the test that walks this list
 * against `STATUS_BY_CODE` is what fails.
 */
export const LIBRARY_CODES = [
  // src/core/ontology.ts
  "SOURCE_UNREADABLE",
  "SOURCE_EMPTY",
  "UNSUPPORTED_SOURCE",
  "BLOCKING_QUESTIONS_OPEN",
  "NO_TRANSITION",
  "NO_INVARIANTS",
  "NOT_ACCEPTED",
  // src/core/ops.ts
  "POLICY_THREW",
  "POLICY_EMPTY",
  "EMPTY_TRAJECTORY",
  "OBJECTIVE_THREW",
  // src/channel/conversation.ts
  "UNANSWERED_BLOCKING",
  "UNKNOWN_QUESTION",
  "EMPTY_REPLY",
] as const;

/** Codes that belong to the transport. The library has no requests, so it cannot raise these. */
export const HUB_CODES = [
  "MALFORMED_BODY",
  "MISSING_FIELD",
  "INVALID_FIELD",
  "PATH_ESCAPES_ROOT",
  "METHOD_NOT_ALLOWED",
  "UNKNOWN_ROUTE",
  "UNKNOWN_PROPOSAL",
  "UNKNOWN_ONTOLOGY",
  "UNKNOWN_RUN",
  "NOT_FOUND",
  "UNEXPECTED",
] as const;

export type LibraryCode = (typeof LIBRARY_CODES)[number];
export type HubCode = (typeof HUB_CODES)[number];

/**
 * Reasoning behind the non-obvious choices:
 *
 *  - BLOCKING_QUESTIONS_OPEN and UNANSWERED_BLOCKING are 409, not 400. The
 *    request is well-formed; the *state of the proposal* refuses it. Retrying
 *    the same request after answering the questions is the intended recovery,
 *    which is exactly what 409 means and 400 does not.
 *  - NOT_ACCEPTED is 403. An ontology nobody accepted is not missing and not
 *    malformed -- it is forbidden to run, which is the entire product.
 *  - NO_TRANSITION / NO_INVARIANTS / POLICY_EMPTY / EMPTY_TRAJECTORY are 422:
 *    the request is understood and the named ontology exists, but what it
 *    describes cannot be executed.
 *  - POLICY_THREW and OBJECTIVE_THREW are 500. Both mean server-side code
 *    supplied by this hub misbehaved. Blaming the caller for that would be a
 *    lie told in a status code.
 *  - PATH_ESCAPES_ROOT is 403 rather than 404. A 404 would leak the fact that
 *    the path resolves to something; the refusal is about the attempt.
 */
export const STATUS_BY_CODE: Readonly<Record<LibraryCode | HubCode, number>> = {
  SOURCE_UNREADABLE: 400,
  SOURCE_EMPTY: 400,
  UNSUPPORTED_SOURCE: 400,
  BLOCKING_QUESTIONS_OPEN: 409,
  NO_TRANSITION: 422,
  NO_INVARIANTS: 422,
  NOT_ACCEPTED: 403,
  POLICY_THREW: 500,
  POLICY_EMPTY: 422,
  EMPTY_TRAJECTORY: 422,
  OBJECTIVE_THREW: 500,
  UNANSWERED_BLOCKING: 409,
  UNKNOWN_QUESTION: 400,
  EMPTY_REPLY: 400,
  MALFORMED_BODY: 400,
  MISSING_FIELD: 400,
  INVALID_FIELD: 400,
  PATH_ESCAPES_ROOT: 403,
  METHOD_NOT_ALLOWED: 405,
  UNKNOWN_ROUTE: 404,
  UNKNOWN_PROPOSAL: 404,
  UNKNOWN_ONTOLOGY: 404,
  UNKNOWN_RUN: 404,
  NOT_FOUND: 404,
  UNEXPECTED: 500,
};

/**
 * An unmapped code is a 500 on purpose. A code this table has never seen means
 * the hub is returning a failure it does not understand, and reporting that as
 * a 4xx would tell the caller to fix something on their side that may be fine.
 */
export function httpStatusFor(code: string): number {
  return (STATUS_BY_CODE as Record<string, number | undefined>)[code] ?? 500;
}
