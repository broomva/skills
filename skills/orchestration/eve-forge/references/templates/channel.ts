// TEMPLATE: agent/channels/<channel>.ts
// AUTH IS LOCKED BY DEFAULT. The scaffold ships placeholderAuth(); this template
// replaces it with a real authenticator so the deploy-safety gate passes.
// NEVER add none() for a production deploy — the gate will (and should) block it.
import { defineChannel } from "eve/channels";
import { vercelOidc, localDev } from "eve/channels/auth";

export default defineChannel({
  // HTTP channel. Add @chat-adapter/whatsapp etc. for WhatsApp/Telegram ingress.
  auth: [vercelOidc(), localDev()], // prod-safe: real authenticator + dev convenience
  // Do NOT ship: auth: [none()]  ← deploy-safety.py denies this in prod (fail-closed).
});
