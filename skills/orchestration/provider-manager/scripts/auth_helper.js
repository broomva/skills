#!/usr/bin/env node

/**
 * auth_helper.js
 * 
 * Helper utility for provider-manager:
 * - Decrypts browser session cookies (Arc / Chrome) from macOS Keychain
 * - Interrogates Claude.ai session & organization state
 * - Executes automated OAuth approval without GUI / browser interaction
 */

const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");

function getSafeStoragePassword(serviceName) {
  try {
    const raw = execFileSync("security", ["find-generic-password", "-s", serviceName, "-w"], { encoding: "utf8" });
    return raw.trim();
  } catch (err) {
    throw new Error(`Failed to read Keychain password for service '${serviceName}': ${err.message}`);
  }
}

function deriveKey(password) {
  const salt = "saltysalt";
  const iterations = 1003;
  return crypto.pbkdf2Sync(password, salt, iterations, 16, "sha1");
}

function decryptCookieValue(blob, key) {
  if (!blob || blob.length < 3) return "";
  const prefix = blob.slice(0, 3).toString("utf8");
  if (prefix !== "v10") return blob.toString("utf8");

  const iv = Buffer.alloc(16, 0x20);
  const decipher = crypto.createDecipheriv("aes-128-cbc", key, iv);
  decipher.setAutoPadding(false);

  try {
    const decrypted = Buffer.concat([decipher.update(blob.slice(3)), decipher.final()]);
    const pad = decrypted[decrypted.length - 1];
    let unpadded = decrypted;
    if (pad > 0 && pad <= 16) {
      unpadded = decrypted.slice(0, decrypted.length - pad);
    }
    return unpadded.slice(32).toString("utf8");
  } catch (e) {
    return "";
  }
}

function getBrowserCookieDirs(browser = "arc") {
  const home = process.env.HOME;
  if (browser.toLowerCase() === "chrome") {
    const base = path.join(home, "Library/Application Support/Google/Chrome");
    return {
      service: "Chrome Safe Storage",
      base,
      profiles: ["Default", "Profile 1", "Profile 2", "Profile 3", "Profile 4"]
    };
  }
  // Default Arc
  const base = path.join(home, "Library/Application Support/Arc/User Data");
  return {
    service: "Arc Safe Storage",
    base,
    profiles: ["Profile 3", "Default", "Profile 1", "Profile 2", "Profile 4", "Profile 5"]
  };
}

function findClaudeCookies(preferredBrowser = "arc", preferredProfile = null) {
  const browsers = preferredBrowser === "chrome" ? ["chrome", "arc"] : ["arc", "chrome"];

  for (const b of browsers) {
    const info = getBrowserCookieDirs(b);
    let password;
    try {
      password = getSafeStoragePassword(info.service);
    } catch {
      continue;
    }
    const key = deriveKey(password);
    const profiles = preferredProfile ? [preferredProfile, ...info.profiles.filter(p => p !== preferredProfile)] : info.profiles;

    for (const profile of profiles) {
      const cookiePath = path.join(info.base, profile, "Cookies");
      if (!fs.existsSync(cookiePath)) continue;

      const tmpDb = `/tmp/pm-cookies-${Date.now()}-${Math.random().toString(36).slice(2)}.db`;
      try {
        fs.copyFileSync(cookiePath, tmpDb);
        const rows = execFileSync(
          "sqlite3",
          [tmpDb, 'SELECT host_key, name, hex(encrypted_value) FROM cookies WHERE host_key LIKE "%claude.ai%";'],
          { encoding: "utf8" }
        );

        const cookieJar = {};
        for (const line of rows.trim().split("\n")) {
          if (!line) continue;
          const [host, name, hex] = line.split("|");
          const val = decryptCookieValue(Buffer.from(hex, "hex"), key);
          if (val) cookieJar[name] = val;
        }

        if (cookieJar.sessionKeyV3 || cookieJar.sessionKey) {
          return {
            browser: b,
            profile,
            cookies: cookieJar,
            cookieHeader: Object.entries(cookieJar).map(([k, v]) => `${k}=${v}`).join("; ")
          };
        }
      } catch (err) {
        // Continue to next profile
      } finally {
        if (fs.existsSync(tmpDb)) {
          try { fs.unlinkSync(tmpDb); } catch {}
        }
      }
    }
  }

  throw new Error("No active Claude session cookies found across Arc and Chrome profiles.");
}

async function getSessionInfo(cookieHeader) {
  const res = await fetch("https://claude.ai/api/bootstrap", {
    headers: {
      "Cookie": cookieHeader,
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      "Accept": "application/json"
    }
  });

  if (!res.ok) {
    throw new Error(`Failed to fetch session bootstrap: HTTP ${res.status}`);
  }

  const data = await res.json();
  const account = data.account || {};
  const memberships = account.memberships || [];
  const primaryOrg = memberships[0]?.organization || {};

  return {
    email: account.email_address,
    displayName: account.display_name,
    fullName: account.full_name,
    accountUuid: account.uuid,
    organizationUuid: primaryOrg.uuid,
    organizationName: primaryOrg.name,
    capabilities: primaryOrg.capabilities || [],
    allOrganizations: memberships.map(m => ({
      uuid: m.organization?.uuid,
      name: m.organization?.name
    }))
  };
}

async function approveOAuth(authUrl, cookieHeader, targetOrgUuid) {
  let currentUrl = authUrl;
  const cookieJar = {};
  for (const part of cookieHeader.split(";")) {
    const [k, ...v] = part.trim().split("=");
    if (k) cookieJar[k] = v.join("=");
  }

  function getHeader() {
    return Object.entries(cookieJar).map(([k, v]) => `${k}=${v}`).join("; ");
  }

  function updateJar(rawSet) {
    if (!rawSet) return;
    const list = Array.isArray(rawSet) ? rawSet : [rawSet];
    for (const h of list) {
      const parts = h.split(";")[0].split("=");
      if (parts.length >= 2) cookieJar[parts[0].trim()] = parts.slice(1).join("=").trim();
    }
  }

  // 1. Follow initial redirects to register the OAuth session
  let finalTargetUrl = currentUrl;
  for (let step = 0; step < 8; step++) {
    const res = await fetch(currentUrl, {
      headers: {
        "Cookie": getHeader(),
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
      },
      redirect: "manual"
    });

    const rawSet = res.headers.getSetCookie ? res.headers.getSetCookie() : [res.headers.get("set-cookie")].filter(Boolean);
    updateJar(rawSet);

    if (res.status >= 300 && res.status < 400) {
      const loc = res.headers.get("location");
      currentUrl = new URL(loc, currentUrl).toString();
      finalTargetUrl = currentUrl;
    } else {
      break;
    }
  }

  const parsedUrl = new URL(finalTargetUrl);
  const clientId = parsedUrl.searchParams.get("client_id") || "9d1c250a-e61b-44d9-88ed-5944d1962f5e";
  const redirectUri = parsedUrl.searchParams.get("redirect_uri") || "https://platform.claude.com/oauth/code/callback";
  let scope = parsedUrl.searchParams.get("scope") || "user:profile user:inference user:sessions:claude_code user:mcp_servers user:file_upload user:plugins";
  // Remove org:create_api_key if present, as claude.ai rejects it for user chat orgs
  scope = scope.replace(/\borg:create_api_key\b/g, "").replace(/\s+/g, " ").trim();

  const state = parsedUrl.searchParams.get("state");
  const codeChallenge = parsedUrl.searchParams.get("code_challenge");
  const codeChallengeMethod = parsedUrl.searchParams.get("code_challenge_method") || "S256";

  if (!state || !codeChallenge) {
    throw new Error("Missing state or code_challenge in authorization URL parameters.");
  }

  // 2. Perform the approval POST
  const approveEndpoint = `https://claude.ai/v1/oauth/${targetOrgUuid}/authorize`;
  const approveRes = await fetch(approveEndpoint, {
    method: "POST",
    headers: {
      "Cookie": getHeader(),
      "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
      "Accept": "application/json",
      "Content-Type": "application/json",
      "Origin": "https://claude.ai",
      "Referer": "https://claude.ai/oauth/authorize"
    },
    body: JSON.stringify({
      response_type: "code",
      client_id: clientId,
      organization_uuid: targetOrgUuid,
      redirect_uri: redirectUri,
      scope: scope,
      state: state,
      code_challenge: codeChallenge,
      code_challenge_method: codeChallengeMethod
    })
  });

  if (!approveRes.ok) {
    const errBody = await approveRes.text();
    throw new Error(`OAuth authorization call failed (HTTP ${approveRes.status}): ${errBody}`);
  }

  const approveData = await approveRes.json();
  if (!approveData.redirect_uri) {
    throw new Error(`No redirect_uri returned: ${JSON.stringify(approveData)}`);
  }

  const resultUrl = new URL(approveData.redirect_uri);
  const code = resultUrl.searchParams.get("code");
  const returnedState = resultUrl.searchParams.get("state") || state;

  if (!code) {
    throw new Error("No authorization code found in redirect URL.");
  }

  return {
    code,
    state: returnedState,
    formattedInput: `${code}#${returnedState}`
  };
}

async function main() {
  const args = process.argv.slice(2);
  const command = args[0];

  try {
    if (command === "find-session") {
      const browser = args[1] || "arc";
      const profile = args[2] || null;
      const res = findClaudeCookies(browser, profile);
      const session = await getSessionInfo(res.cookieHeader);
      console.log(JSON.stringify({
        browser: res.browser,
        profile: res.profile,
        session
      }, null, 2));
    } else if (command === "approve-oauth") {
      const authUrl = args[1];
      const orgUuid = args[2];
      const browser = args[3] || "arc";
      const profile = args[4] || null;

      if (!authUrl || !orgUuid) {
        console.error("Usage: auth_helper.js approve-oauth <authUrl> <orgUuid> [browser] [profile]");
        process.exit(1);
      }

      const res = findClaudeCookies(browser, profile);
      const result = await approveOAuth(authUrl, res.cookieHeader, orgUuid);
      console.log(JSON.stringify(result, null, 2));
    } else {
      console.error("Unknown command:", command);
      process.exit(1);
    }
  } catch (err) {
    console.error(JSON.stringify({ error: err.message }));
    process.exit(1);
  }
}

if (require.main === module) {
  main();
}
