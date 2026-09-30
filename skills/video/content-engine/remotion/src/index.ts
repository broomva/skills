import { registerRoot } from "remotion";
import { RemotionRoot } from "./Root";

// Entry point for `remotion render src/index.ts <composition>`. Without it the
// CLI has nothing to bundle and render.sh cannot render at all.
registerRoot(RemotionRoot);
