#!/usr/bin/env bun
/**
 * The `parallax` command.
 *
 * A shim, deliberately: `src/cli.ts` stays importable and testable, and this
 * file exists only so `package.json`'s `bin` has something with a shebang to
 * point at. Everything it can do, `runCli` does -- there is no behaviour here to
 * diverge from the tool surface.
 *
 * `src/cli.ts` guards its own entry with `import.meta.main`, which is false when
 * it is imported, so nothing runs twice.
 */
import { runCli } from "../src/cli";

process.exitCode = await runCli(process.argv.slice(2));
