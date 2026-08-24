"use client";

import { useId, useState } from "react";

/**
 * The same three operations, three ways in. The point of the section is that
 * they are the same handler functions underneath, so the snippets are the real
 * ones -- the CLI usage strings come out of the runtime's src/cli.ts, the routes
 * out of src/hub/app.ts and the tool names out of src/tools/index.ts
 * (skills/simulation/parallax/runtime/).
 */

type Way = { id: string; label: string; say: string; code: React.ReactNode };

const WAYS: Way[] = [
  {
    id: "cli",
    label: "CLI",
    say: "Seven commands. Every one of them takes --json and prints a value, so a shell script never has to parse prose.",
    code: (
      <>
        {"$ "}
        <b>parallax propose</b>
        {" --kind filesystem --root ./ --json\n"}
        {"$ "}
        <b>parallax accept</b>
        {" --proposal p-4c1e --answer src.count=files --by carlos --json\n"}
        {"$ "}
        <b>parallax run</b>
        {" --horizon 12 --seed 42 --governed --json\n"}
        {"$ "}
        <b>parallax receipt</b>
        {" --run bef312a9 --out out/run.html\n"}
        <span className="c">
          {"\n# --ontology is optional: omitted means the newest acceptance"}
        </span>
      </>
    ),
  },
  {
    id: "http",
    label: "HTTP",
    say: "Four routes and a receipt URL. /health reports the commit the server is running, which is the only field on it a stale image cannot fake.",
    code: (
      <>
        {"POST "}
        <b>/api/ontology/propose</b>
        {"     → proposal | error.code\n"}
        {"POST "}
        <b>/api/ontology/accept</b>
        {"      → active   | BLOCKING_QUESTIONS_OPEN\n"}
        {"POST "}
        <b>/api/run</b>
        {"                   → receipt  | trajectory + trace hash\n"}
        {"POST "}
        <b>/api/whatsapp/turn</b>
        {"        → the whole product as one thread\n"}
        {"GET  "}
        <b>/r/:id</b>
        {"                    → the receipt, as a page\n"}
        {"GET  "}
        <b>/health</b>
        {'                   → {"commit": "d800f1045a01"}'}
      </>
    ),
  },
  {
    id: "tool",
    label: "Agent tool",
    say: "Eight tools over the same handlers. Every failure is a value with a stable code rather than a thrown string a caller has to read, and the error types are per-operation: a plugin failure inside a rollout carries the partial trajectory, the same failure at registration carries nothing.",
    code: (
      <>
        <b>parallax_propose_ontology</b>
        {"  { kind, root?, tables? }\n"}
        <b>parallax_render_proposal</b>
        {"   { proposalId }\n"}
        <b>parallax_parse_reply</b>
        {"       { proposalId, text }\n"}
        <b>parallax_answer_questions</b>
        {"  { proposalId, answers }\n"}
        <b>parallax_accept_ontology</b>
        {"   { proposalId, acceptedBy }\n"}
        <b>parallax_reject_proposal</b>
        {"   { proposalId, reason }\n"}
        <b>parallax_run</b>
        {"               { ontologyId?, horizon, seed }\n"}
        <b>parallax_receipt</b>
        {"           { runId }"}
      </>
    ),
  },
];

export function Surface() {
  const [active, setActive] = useState(WAYS[0].id);
  const uid = useId();
  const way = WAYS.find((w) => w.id === active) ?? WAYS[0];

  return (
    <div className="tabs">
      <div className="tabbar" role="tablist" aria-label="Ways in">
        {WAYS.map((w) => (
          <button
            key={w.id}
            type="button"
            role="tab"
            id={`${uid}-${w.id}`}
            aria-selected={w.id === active}
            aria-controls={`${uid}-panel`}
            onClick={() => setActive(w.id)}
          >
            {w.label}
          </button>
        ))}
      </div>
      <div
        className="tabpanel"
        role="tabpanel"
        id={`${uid}-panel`}
        aria-labelledby={`${uid}-${way.id}`}
      >
        <pre>
          <code>{way.code}</code>
        </pre>
        <p className="t-say">{way.say}</p>
      </div>
    </div>
  );
}
