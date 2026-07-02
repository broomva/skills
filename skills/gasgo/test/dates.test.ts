import { expect, test } from "bun:test";
import { parseSocrataDate, toIsoDate } from "../src/dates.ts";

test("parses non-padded Socrata dates correctly", () => {
  expect(toIsoDate("2025-9-01")).toBe("2025-09-01");
  expect(toIsoDate("2026-6-01")).toBe("2026-06-01");
});

test("non-lexical ordering: Sept must be < Dec (the gotcha)", () => {
  const sep = parseSocrataDate("2025-9-01").getTime();
  const dec = parseSocrataDate("2025-12-01").getTime();
  // Lexically "2025-9-01" > "2025-12-01"; parsed, Sept must come first.
  expect(sep).toBeLessThan(dec);
});
