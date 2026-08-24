import { describe, expect, test } from "bun:test";
import { parseReply, renderProposal, resolveAccept } from "../src/channel/conversation";
import type { OntologyProposal } from "../src/core/ontology";
import { activate, proposeOntology, worldOf } from "../src/core/ontology";

function proposal(): OntologyProposal {
  const p = proposeOntology({ kind: "agent-workspace", root: "./src" });
  if (!p.ok) throw new Error("proposal failed");
  return p.value;
}

function allAnswers(p: OntologyProposal): string {
  const blocking = p.openQuestions.filter((q) => q.blocking);
  return `${blocking.map((_, i) => `${i + 1}. units`).join("\n")}\nacepto`;
}

describe("rendering for a channel that cannot edit", () => {
  test("every chunk stays inside a WhatsApp-safe length", () => {
    for (const m of renderProposal(proposal())) expect(m.text.length).toBeLessThanOrEqual(3900);
  });
  test("chunks are numbered so a split message is still readable in order", () => {
    const msgs = renderProposal(proposal());
    expect(msgs.every((m, i) => m.part === i + 1 && m.of === msgs.length)).toBe(true);
  });
  test("each state field carries what it was read from", () => {
    expect(
      renderProposal(proposal())
        .map((m) => m.text)
        .join("\n"),
    ).toContain("<- directory");
  });
  test("the proposal says nothing runs until accepted", () => {
    expect(renderProposal(proposal())[0]?.text).toContain("Nothing runs until you accept it");
  });
});

describe("reading a human reply typed on a phone", () => {
  const qs = proposal().openQuestions;

  test.each([
    ["1. cents", "answers"],
    ["1) cents", "answers"],
    ["1: cents", "answers"],
    ["1 - cents", "answers"],
  ])("accepts %p as a numbered answer", (reply, kind) => {
    expect(parseReply(reply, qs).kind).toBe(kind as "answers");
  });

  test.each(["accept", "acepto", "ACEPTAR", "ok", "listo", "dale", "sí"])(
    "reads %p as acceptance",
    (reply) => {
      expect(parseReply(reply, qs).kind).toBe("accept");
    },
  );

  test.each(["reject", "rechazar", "no", "cancel"])("reads %p as rejection", (reply) => {
    expect(parseReply(reply, qs).kind).toBe("reject");
  });

  test("an ambiguous reply containing both resolves to reject, never accept", () => {
    expect(parseReply("accept but also reject", qs).kind).toBe("reject");
  });

  test("an unparseable reply is unclear rather than a guess", () => {
    expect(parseReply("??", qs).kind).toBe("unclear");
    expect(parseReply("   ", qs).kind).toBe("unclear");
  });
});

describe("resolving an accept against the proposal", () => {
  test("bare acceptance with open questions is refused and names what is missing", () => {
    const p = proposal();
    const r = resolveAccept(parseReply("acepto", p.openQuestions), p);
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("UNANSWERED_BLOCKING");
      expect((r.error.detail?.slots as string[] | undefined)?.length).toBe(
        p.openQuestions.filter((q) => q.blocking).length,
      );
    }
  });

  test("partial answers are refused and name only the remainder", () => {
    const p = proposal();
    const blocking = p.openQuestions.filter((q) => q.blocking);
    const r = resolveAccept(parseReply("1. units\nacepto", p.openQuestions), p);
    expect(r.ok).toBe(false);
    if (!r.ok)
      expect((r.error.detail?.slots as string[] | undefined)?.length).toBe(blocking.length - 1);
  });

  test("a rejection is not treated as an accept", () => {
    const p = proposal();
    expect(resolveAccept(parseReply("no", p.openQuestions), p).ok).toBe(false);
  });

  test("full answers plus acceptance activates -- the control", () => {
    const p = proposal();
    const r = resolveAccept(parseReply(allAnswers(p), p.openQuestions), p);
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const a = activate(p, {
      transition: (s) => s,
      invariants: [{ name: "nonneg", kind: "conservation", check: () => null }],
      answered: r.value.answered,
      acceptedBy: "+57 300 000 0000",
      at: 1756000000,
    });
    expect(a.ok).toBe(true);
    if (a.ok) {
      expect(worldOf(a.value).ok).toBe(true);
      expect(a.value.acceptedBy).toBe("+57 300 000 0000");
    }
  });
});

describe("chunking belongs to the transport, not the proposal", () => {
  test("a buffering channel receives the proposal as one message", () => {
    expect(renderProposal(proposal()).length).toBe(1);
  });
  test("a channel with a tighter limit gets it split, numbered in order", () => {
    const msgs = renderProposal(proposal(), 300);
    expect(msgs.length).toBeGreaterThan(1);
    expect(msgs.every((m, i) => m.part === i + 1 && m.of === msgs.length)).toBe(true);
    for (const m of msgs) expect(m.text.length).toBeLessThanOrEqual(400);
  });
});
