import assert from "node:assert/strict";
import { test } from "node:test";
import { pickSelftestHarnesses } from "../src/selftest.js";

test("pickSelftestHarnesses supports Claude-only, Codex-only, T3-only, and explicit override", () => {
  assert.deepEqual(pickSelftestHarnesses({ claude: false, codex: false, t3: true }, {}), {
    claude: false,
    codex: false,
    t3: true,
    editHarness: "t3",
  });
  assert.deepEqual(pickSelftestHarnesses({ claude: false, codex: true, t3: false }, {}), {
    claude: false,
    codex: true,
    t3: false,
    editHarness: "codex",
  });
  assert.deepEqual(
    pickSelftestHarnesses({ claude: true, codex: true, t3: true }, { ANA_EDIT_HARNESS: "codex" }),
    {
      claude: true,
      codex: true,
      t3: true,
      editHarness: "codex",
    },
  );
  assert.deepEqual(pickSelftestHarnesses({ claude: false, codex: false, t3: false }, {}), {
    claude: false,
    codex: false,
    t3: false,
    editHarness: null,
  });
});
