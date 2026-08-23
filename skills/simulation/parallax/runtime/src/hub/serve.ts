/**
 * Deploy entrypoint.
 *
 * A one-line file with a stable path, so the platform's start command does not
 * name a module that also exports things. `src/hub/index.ts` starts the server
 * too when it is the process entrypoint; this exists so that a start command
 * reads as an instruction rather than as a side effect of importing a library.
 */
import { startHub } from "./index";

startHub();
