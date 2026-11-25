import assert from "node:assert/strict";
import { test } from "node:test";
import { BUNDLE_ID_PREFIX, icnsFromPngs, infoPlist, parseCdhash } from "../src/bundle.js";

const keys = {
  installId: "agent-pad-1a2b",
  name: "Agent & Pad",
  hostPath: "/Applications/Host.app",
  hostBundleId: "com.example.host",
  serverName: "agent-native-apps-deadbeef",
  launchArguments: ["/src/root", "--home=/h"],
  hasIcon: true,
};

test("Info.plist names the host and the shim server", () => {
  const plist = infoPlist(keys);
  assert.match(plist, /<key>ElectronAppShimHostPath<\/key><string>\/Applications\/Host.app<\/string>/);
  assert.match(plist, /<key>ElectronAppShimServerName<\/key><string>agent-native-apps-deadbeef<\/string>/);
  assert.match(
    plist,
    /<key>ElectronAppShimHostArguments<\/key><array><string>\/src\/root<\/string><string>--home=\/h<\/string><\/array>/,
  );
  assert.ok(plist.includes(`<string>${BUNDLE_ID_PREFIX}agent-pad-1a2b</string>`));
  assert.ok(plist.includes("<string>Agent &amp; Pad</string>"), "names are XML-escaped");
  assert.ok(plist.includes("<key>CFBundleIconFile</key>"));
  assert.ok(!infoPlist({ ...keys, hasIcon: false }).includes("CFBundleIconFile"));
});

test("parseCdhash reads codesign -dvvv output", () => {
  const out =
    "Executable=/x\nIdentifier=a\nCDHash=aad66434f1bb28eb5b4ce8d0967e749daa152077\nSignature=adhoc\n";
  assert.equal(parseCdhash(out), "aad66434f1bb28eb5b4ce8d0967e749daa152077");
  assert.equal(parseCdhash("Signature=adhoc"), null);
});

test("icnsFromPngs writes a well-formed container", () => {
  const png = Buffer.from("png-bytes");
  const icns = icnsFromPngs({ 128: png, 256: png });
  assert.equal(icns.subarray(0, 4).toString("latin1"), "icns");
  assert.equal(icns.readUInt32BE(4), icns.length);
  // ic07 (128) then ic13 + ic08 (256): three chunks of 8 + 9 bytes.
  assert.equal(icns.length, 8 + 3 * (8 + png.length));
  assert.equal(icns.subarray(8, 12).toString("latin1"), "ic07");
});
