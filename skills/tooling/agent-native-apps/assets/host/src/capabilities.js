// The capability table and the gate every bridge call passes through.
//
// Tier 1 needs nothing beyond being an installed app. Tier 2 and 3 each need
// two things: the app's manifest declares the permission, and the user granted
// it for the app's CURRENT version. A grant for an older version does not count,
// so an app that edits itself (or is edited by its agent) asks again.

export const TIERS = { BASIC: 1, PERMISSION: 2, FULL: 3 };

// permission name -> tier.
// Every agent run is tier 3. A harness runs as the user with the app folder as
// its working directory and a reduced tool list, but no OS sandbox: a read-only
// Claude run can still Read an absolute path, and Codex runs shell commands.
// `agent` = may read; `agent-edit` = may also change the app's files. A t3 run
// always needs `agent-edit`, because T3 threads take their project's runtime
// mode and the CLI has no read-only switch.
export const PERMISSIONS = {
  notifications: TIERS.PERMISSION,
  "menu-bar": TIERS.PERMISSION,
  shortcuts: TIERS.PERMISSION,
  agent: TIERS.FULL,
  "agent-edit": TIERS.FULL,
  "full-access": TIERS.FULL,
};

// "module.method" -> permission required (null = tier 1, no permission).
export const METHODS = {
  "window.setTitle": null,
  "window.setBounds": null,
  "window.getBounds": null,
  "dock.setBadge": null,
  "dock.bounce": null,
  "app.info": null,
  "permissions.state": null,
  "permissions.request": null,
  "notification.show": "notifications",
  "tray.set": "menu-bar",
  "tray.remove": null,
  "globalShortcut.register": "shortcuts",
  "globalShortcut.unregisterAll": null,
  "agent.run": "agent",
  "agent.cancel": null,
  "fs.readFile": "full-access",
  "fs.writeFile": "full-access",
  "fs.readdir": "full-access",
};

export class CapabilityError extends Error {
  constructor(code, message) {
    super(message);
    this.code = code;
  }
}

/** Parse a policy ceiling; anything but 1, 2 or 3 is refused. Pure. */
export function parseMaxTier(value) {
  const n = Number(value);
  if (!Number.isInteger(n) || n < 1 || n > 3)
    throw new Error(`--max-tier must be 1, 2 or 3, not "${value}".`);
  return n;
}

/**
 * The permission a call needs. `agent.run` escalates to `agent-edit` for
 * `{edit:true}` and for the t3 harness. The harness must already be resolved
 * (args[0].harness), since the page may omit it.
 */
export function requiredPermission(module, method, args = []) {
  const key = `${module}.${method}`;
  if (!Object.hasOwn(METHODS, key)) return undefined;
  const permission = METHODS[key];
  if (key === "agent.run" && (args[0]?.edit === true || args[0]?.harness === "t3")) return "agent-edit";
  return permission;
}

export const tierOf = (permission) => (permission === null ? TIERS.BASIC : PERMISSIONS[permission]);

/**
 * Decide a call. Pure: no I/O, so the whole policy is testable.
 * @param {{module:string, method:string, args?:unknown[]}} call
 * @param {{declared:Set<string>, granted:Set<string>, maxTier:number}} ctx
 *   declared = manifest permissions; granted = grants for the current version;
 *   maxTier = the host policy ceiling.
 * @returns {{ok:true, permission:string|null, tier:number} | {ok:false, code:string, permission?:string, message:string}}
 */
export function decide(call, ctx) {
  const permission = requiredPermission(call.module, call.method, call.args);
  if (permission === undefined) {
    return { ok: false, code: "ENOSYS", message: `There is no ${call.module}.${call.method}.` };
  }
  const tier = tierOf(permission);
  // Written as !(<=) so a NaN or missing ceiling refuses instead of allowing.
  if (!(tier <= ctx.maxTier)) {
    return {
      ok: false,
      code: "EPOLICY",
      permission,
      message: `The host policy allows tier ${ctx.maxTier}; ${call.module}.${call.method} is tier ${tier}.`,
    };
  }
  if (permission === null) return { ok: true, permission, tier };
  if (!ctx.declared.has(permission)) {
    return {
      ok: false,
      code: "ENOTDECLARED",
      permission,
      message: `"${permission}" is not in this app's app.json permissions.`,
    };
  }
  if (!ctx.granted.has(permission)) {
    return {
      ok: false,
      code: "EPERM",
      permission,
      message: `"${permission}" is not granted for this version of the app.`,
    };
  }
  return { ok: true, permission, tier };
}
