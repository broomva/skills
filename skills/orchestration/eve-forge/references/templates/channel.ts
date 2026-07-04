// TEMPLATE: agent/channels/eve.ts
// NOTE (BRO-1685): `npx eve init` ALREADY scaffolds this file with the correct
// wrapper — `eveChannel` from `eve/channels/eve`. Its default `auth` array ends
// with `placeholderAuth()`. The AUTHOR stage EDITS the scaffolded file to remove
// placeholderAuth() and lock to a real authenticator. Do NOT hand-write
// `defineChannel` from `eve/channels` (that is the generic channel and needs routes).
import { eveChannel } from "eve/channels/eve";
import { localDev, vercelOidc } from "eve/channels/auth";

export default eveChannel({
  auth: [vercelOidc(), localDev()], // prod-safe: real authenticator + dev convenience
  // NEVER ship: auth: [none()] — and remove placeholderAuth() — deploy_safety.py blocks both (fail-closed).
});
