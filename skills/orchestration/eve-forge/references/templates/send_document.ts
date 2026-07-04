// TEMPLATE: agent/tools/send_document.ts
// Delivery is APPROVAL-GATED — `always()` pauses the run for human confirmation
// before the side-effect fires (the benchmark proved this pause→approve→execute loop).
import { defineTool } from "eve/tools";
import { always } from "eve/tools/approval";
import { z } from "zod";

export default defineTool({
  description: "Deliver a produced document to a recipient. Requires human approval.",
  approval: always(),
  inputSchema: z.object({
    recipient: z.string().describe("email / phone of the recipient"),
    path: z.string().describe("path of the produced document"),
    note: z.string().optional(),
  }),
  async execute({ recipient, path, note }) {
    // TODO(author): wire the real delivery adapter (Resend / WhatsApp Cloud API).
    return { delivered: true, recipient, path, note, sentAt: new Date().toISOString() };
  },
});
