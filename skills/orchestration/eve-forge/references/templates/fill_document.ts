// TEMPLATE: agent/tools/fill_document.ts
// The model composes `filled_document`; this tool persists it durably + an audit
// sidecar and returns a receipt. No hidden second LLM call in the tool.
import { defineTool } from "eve/tools";
import { z } from "zod";
import { writeFile, mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";

export default defineTool({
  description: "Persist the filled document composed by the model, with an audit record.",
  inputSchema: z.object({
    template: z.string().describe("the business's blank template"),
    transcript: z.string().describe("the source conversation"),
    filled_document: z.string().describe("the model-composed filled document"),
    slug: z.string().describe("tenant + case slug, e.g. vet-bella"),
  }),
  async execute({ template, transcript, filled_document, slug }) {
    const path = join("/tmp/docfill", `${slug}.md`);
    await mkdir(dirname(path), { recursive: true });
    await writeFile(path, filled_document);
    // audit sidecar (provenance: what produced this doc)
    await writeFile(path + ".audit.json", JSON.stringify({
      slug, at: new Date().toISOString(),
      template_len: template.length, transcript_len: transcript.length,
      bytes: Buffer.byteLength(filled_document),
    }, null, 2));
    return { path, bytes: Buffer.byteLength(filled_document) };
  },
});
