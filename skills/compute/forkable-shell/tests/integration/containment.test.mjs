// The security claim: an agent given only the vbash tool cannot read the host.
// Tested against the tool itself, deterministically -- not through a model.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as nfs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { World } from "../../scripts/world.mjs";

const CANARY = "CANARY-a7f3e9-TOPSECRET";
const tmp = () => nfs.mkdtempSync(path.join(os.tmpdir(), "contain-"));

async function probeWorld() {
  const d = tmp();
  nfs.writeFileSync(path.join(d, "host-canary.txt"), CANARY + "\n");
  return { world: await World.open(path.join(d, "w.json")), dir: d };
}

test("no host path is reachable from inside the world", async () => {
  const { world, dir } = await probeWorld();
  const probes = [
    `cat ${dir}/host-canary.txt`,
    "cat /etc/hosts",
    "cat /work/../../../etc/hosts",
    `ls ${os.homedir()}`,
    `cat ${path.resolve(dir)}/host-canary.txt`,
    "grep -rl CANARY / 2>/dev/null | head",
    "env | grep -i -E 'key|token|secret|aws|anthropic' | head",
    "cat /proc/self/environ 2>/dev/null",
  ];
  for (const p of probes) {
    const r = await world.exec(p);
    assert.ok(!`${r.stdout}${r.stderr}`.includes("TOPSECRET"), `host content leaked via: ${p}`);
  }
});

test("POSITIVE CONTROL: the probe detects a canary planted inside the world", async () => {
  const { world } = await probeWorld();
  await world.exec(`echo '${CANARY}' > /work/planted.txt`);
  const r = await world.exec("cat /work/planted.txt");
  assert.ok(r.stdout.includes("TOPSECRET"),
    "probe cannot detect a leak it should catch -- the containment test above is vacuous");
});

test("writes inside the world never touch the host filesystem", async () => {
  const { world, dir } = await probeWorld();
  const before = nfs.readdirSync(dir).sort();
  await world.exec("mkdir -p /work/deep/nested && echo x > /work/deep/nested/f.txt");
  await world.exec(`echo escape > ${dir}/should-not-appear.txt`);
  const after = nfs.readdirSync(dir).sort();
  assert.deepEqual(after, before, "the world wrote to the host filesystem");
});
