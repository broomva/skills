#!/usr/bin/env python3
"""recon_macos_app — facts and a ranked route list for one macOS .app bundle.

Usage:  recon_macos_app.py <target> [--json] [--arch arm64|x86_64] [--no-codesign] [--home DIR]

<target> is a path to Foo.app, or a bare name looked up as /Applications/<name>.app and
~/Applications/<name>.app.

Read-only. It reads Info.plist and product/package manifests, lists bundle folders, reads
asar headers (the file index, never the code), scans the Electron fuse wire in the slice
that runs on this machine, runs `codesign -d` when it exists, and checks whether the usual
state folders exist. It never launches the app and never opens a profile.

Output: facts (bundle, stack, extension points, protections, update channels, state
locations, caveats) and routes: one entry per rung option with a status
(available · caveat · blocked) and the reason, ranked cheapest-available first.
Home-directory paths are printed as ~/... so the output can be shared.

Exit 0 ok · 2 usage error or not an app bundle. Pure stdlib.
"""
from __future__ import annotations

import argparse
import json
import mmap
import os
import platform
import plistlib
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path
from typing import Callable

# electron/fuses src/constants.ts: sentinel, then version byte, length byte, one byte per fuse.
FUSE_SENTINEL = b"dL7pKGdnNz796PbbjQWNKmHXBZaB9tsX"
FUSE_NAMES = (
    "RunAsNode",
    "EnableCookieEncryption",
    "EnableNodeOptionsEnvironmentVariable",
    "EnableNodeCliInspectArguments",
    "EnableEmbeddedAsarIntegrityValidation",
    "OnlyLoadAppFromAsar",
    "LoadBrowserProcessSpecificV8Snapshot",
    "GrantFileProtocolExtraPrivileges",
    "WasmTrapHandlers",
)
FUSE_STATE = {0x30: "off", 0x31: "on", 0x72: "removed"}
CPU_TYPES = {"arm64": 0x0100000C, "x86_64": 0x01000007}
FAT_MAGICS = {b"\xca\xfe\xba\xbe": 20, b"\xca\xfe\xba\xbf": 32}  # fat_arch / fat_arch_64 sizes

# Extension APIs that a bundle does not advertise in a machine-readable way. Each entry is a
# fact someone checked, not a guess; keep the list short and say where it came from.
KNOWN_APIS: dict[str, list[dict]] = {
    "md.obsidian": [
        {"rung": "2", "kind": "plugin-api", "name": "Obsidian community plugin API",
         "detail": "<vault>/.obsidian/plugins/<id>/ (manifest.json + main.js); per vault. "
                   "Plugins load only after the vault leaves restricted mode, a per-vault "
                   "consent the app stores in its localStorage (enable-plugin-<appId>)."},
        {"rung": "1", "kind": "css", "name": "Obsidian CSS snippets and themes",
         "detail": "<vault>/.obsidian/snippets/*.css, enabled in Settings > Appearance"},
    ],
    "dev.zed.Zed": [
        {"rung": "2", "kind": "plugin-api", "name": "Zed extensions",
         "detail": "Rust compiled to WebAssembly: languages and language servers, themes, "
                   "slash commands, context servers; dev extensions install from a folder"},
        {"rung": "1", "kind": "config", "name": "Zed settings.json, keymap.json and themes",
         "detail": "~/.config/zed/"},
    ],
}

# Rank inside rung 2: what can add behaviour beats what can only trigger it.
RUNG2_ORDER = ("plugin-api", "vscode-extensions", "applescript", "app-intents", "cli",
               "url-scheme", "services", "accessibility")
STATUS_ORDER = {"available": 0, "caveat": 1, "blocked": 2}

Runner = Callable[[list[str]], "subprocess.CompletedProcess[str]"]


class NotABundle(Exception):
    pass


# ---------------------------------------------------------------- helpers

def tilde(p: Path | str, home: Path) -> str:
    """Print home paths as ~/... so the output never carries a user name."""
    s = str(p)
    h = str(home)
    if s == h:
        return "~"
    if s.startswith(h.rstrip("/") + "/"):
        return "~/" + s[len(h.rstrip("/")) + 1:]
    return s


def resolve_target(target: str, home: Path) -> Path:
    p = Path(target).expanduser()
    if p.suffix != ".app" and not p.exists():
        for base in (Path("/Applications"), home / "Applications"):
            cand = base / f"{target}.app"
            if cand.exists():
                p = cand
                break
    if not (p / "Contents" / "Info.plist").is_file():
        raise NotABundle(f"not an app bundle (no Contents/Info.plist): {target}")
    return p


def read_plist(p: Path) -> dict:
    try:
        with p.open("rb") as f:
            d = plistlib.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def listdir(p: Path) -> list[str]:
    try:
        return sorted(os.listdir(p))
    except OSError:
        return []


def asar_index(p: Path) -> dict | None:
    """The asar header: a Chromium pickle holding a JSON file index. Reads the index only."""
    try:
        with p.open("rb") as f:
            head = f.read(16)
            if len(head) < 16:
                return None
            _, header_size, _, json_len = struct.unpack("<IIII", head)
            if json_len <= 0 or json_len > 64 * 1024 * 1024:
                return None
            index = json.loads(f.read(json_len))
            index["_base"] = 8 + header_size
            return index
    except Exception:
        return None


def asar_read_small(p: Path, name: str, limit: int = 256 * 1024) -> bytes | None:
    """Read one small top-level file (a manifest) out of an asar. Manifests only."""
    idx = asar_index(p)
    if not idx:
        return None
    e = idx.get("files", {}).get(name)
    if not e or "offset" not in e or e.get("size", limit + 1) > limit:
        return None
    try:
        with p.open("rb") as f:
            f.seek(idx["_base"] + int(e["offset"]))
            return f.read(int(e["size"]))
    except Exception:
        return None


# ---------------------------------------------------------------- fuses

def _slices(mm: mmap.mmap) -> list[tuple[int, int, int]]:
    """(cputype, offset, size) per slice of a universal binary; [] when it is thin."""
    width = FAT_MAGICS.get(mm[:4])
    if not width:
        return []
    n = struct.unpack(">I", mm[4:8])[0]
    out = []
    for k in range(min(n, 16)):
        base = 8 + width * k
        if width == 20:
            cpu, _sub, off, size, _al = struct.unpack(">IIIII", mm[base:base + 20])
        else:
            cpu, _sub, off, size, _al, _res = struct.unpack(">IIQQII", mm[base:base + 32])
        out.append((cpu, off, size))
    return out


def _wire_at(mm: mmap.mmap, start: int, end: int) -> list[str] | None:
    i = mm.find(FUSE_SENTINEL, start, end)
    if i < 0:
        return None
    j = i + len(FUSE_SENTINEL)
    length = mm[j + 1]
    raw = mm[j + 2:j + 2 + length]
    return [FUSE_STATE.get(b, f"0x{b:02x}") for b in raw]


def read_fuses(binary: Path, arch: str) -> dict | None:
    """The fuse wire in the slice for `arch`, and whether every slice agrees."""
    try:
        with binary.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as mm:
            slices = _slices(mm)
            names = {v: k for k, v in CPU_TYPES.items()}
            if not slices:
                # A thin Mach-O: 0xfeedfacf little-endian, cputype right after the magic.
                cpu = struct.unpack("<I", mm[4:8])[0] if mm[:4] == b"\xcf\xfa\xed\xfe" else None
                chosen = names.get(cpu, "thin") if cpu is not None else "thin"
                wires = {chosen: _wire_at(mm, 0, len(mm))}
            else:
                wires = {names.get(cpu, hex(cpu)): _wire_at(mm, off, off + size)
                         for cpu, off, size in slices}
                chosen = arch if arch in wires else next(iter(wires))
    except (OSError, ValueError):
        return None
    wire = wires.get(chosen)
    if wire is None:
        return {"found": False, "slice": chosen}
    fuses = {(FUSE_NAMES[k] if k < len(FUSE_NAMES) else f"fuse{k}"): v for k, v in enumerate(wire)}
    present = [w for w in wires.values() if w is not None]
    return {"found": True, "slice": chosen, "count": len(wire), "fuses": fuses,
            "slices": sorted(wires), "slices_agree": all(w == present[0] for w in present)}


# ---------------------------------------------------------------- codesign

def default_runner(cmd: list[str]) -> "subprocess.CompletedProcess[str]":
    return subprocess.run(cmd, capture_output=True, text=True, timeout=30)


def read_signature(app: Path, runner: Runner | None) -> dict:
    if runner is None:
        return {"checked": False, "why": "codesign not run (--no-codesign or not on macOS)"}
    try:
        info = runner(["codesign", "-dv", "--verbose=2", str(app)])
        ents = runner(["codesign", "-d", "--entitlements", "-", "--xml", str(app)])
    except (OSError, subprocess.SubprocessError) as e:
        return {"checked": False, "why": f"codesign failed: {e}"}
    # codesign names the bundle by its absolute path; keep only the bundle name so the
    # output stays shareable (the docstring's promise that home paths never appear).
    text = ((info.stdout or "") + (info.stderr or "")).replace(str(app), app.name)
    if info.returncode != 0:
        return {"checked": True, "signed": False, "detail": text.strip()[:200]}
    team = re.search(r"^TeamIdentifier=(.+)$", text, re.M)
    flags = re.search(r"flags=0x[0-9a-f]+\(([^)]*)\)", text)
    ent: dict = {}
    raw = (ents.stdout or "").strip()
    if raw.startswith("<?xml") or raw.startswith("<plist"):
        try:
            ent = plistlib.loads(raw.encode())
        except Exception:
            ent = {}
    team_id = team.group(1).strip() if team else None
    return {
        "checked": True,
        "signed": True,
        "team_id": None if team_id in (None, "not set") else team_id,
        "hardened_runtime": bool(flags and "runtime" in flags.group(1)),
        "sandbox": bool(ent.get("com.apple.security.app-sandbox")),
        "disable_library_validation": bool(ent.get("com.apple.security.cs.disable-library-validation")),
        "allow_jit": bool(ent.get("com.apple.security.cs.allow-jit")),
        "apple_events": bool(ent.get("com.apple.security.automation.apple-events")),
    }


# ---------------------------------------------------------------- recon

def detect_stack(app: Path, info: dict, frameworks: list[str]) -> dict:
    c = app / "Contents"
    ev: list[str] = []
    kind = "native"
    if "Electron Framework.framework" in frameworks:
        kind = "electron"
        ev.append("Contents/Frameworks/Electron Framework.framework")
    elif "Chromium Embedded Framework.framework" in frameworks:
        kind = "cef"
        ev.append("Contents/Frameworks/Chromium Embedded Framework.framework")
    elif "FlutterMacOS.framework" in frameworks:
        kind = "flutter"
        ev.append("Contents/Frameworks/FlutterMacOS.framework")
    elif "QtCore.framework" in frameworks:
        kind = "qt"
        ev.append("Contents/Frameworks/QtCore.framework")
    elif (app / "WrappedBundle").exists() or (app / "Wrapper").is_dir():
        kind = "ios-on-mac"
        ev.append("WrappedBundle / Wrapper")
    elif any((c / d).exists() for d in ("Java", "Eclipse", "jbr")):
        kind = "java"
        ev.append(next(f"Contents/{d}" for d in ("Java", "Eclipse", "jbr") if (c / d).exists()))
    elif "UIDeviceFamily" in info:
        kind = "catalyst"
        ev.append("Info.plist UIDeviceFamily")
    return {"kind": kind, "evidence": ev}


def electron_facts(app: Path, arch: str) -> dict:
    c = app / "Contents"
    fw = c / "Frameworks" / "Electron Framework.framework"
    out: dict = {}
    ver = read_plist(fw / "Resources" / "Info.plist").get("CFBundleVersion")
    if ver:
        out["electron_version"] = ver
    res = c / "Resources"
    code = [n for n in listdir(res) if n.endswith(".asar")]
    if (res / "app").is_dir():
        code.append("app/")
    out["app_code"] = [f"Contents/Resources/{n}" for n in code]
    binary = fw / "Electron Framework"
    if not binary.exists():
        binary = fw / "Versions" / "A" / "Electron Framework"
    fz = read_fuses(binary, arch) if binary.exists() else None
    if fz:
        out["fuse_wire"] = fz
    return out


def vscode_family(app: Path) -> dict | None:
    """VS Code and its forks carry product.json, unpacked under app/ or inside app.asar."""
    res = app / "Contents" / "Resources"
    raw = None
    src = None
    if (res / "app" / "product.json").is_file():
        raw = (res / "app" / "product.json").read_bytes()
        src = "Contents/Resources/app/product.json"
    elif (res / "app.asar").is_file():
        raw = asar_read_small(res / "app.asar", "product.json")
        src = "Contents/Resources/app.asar:product.json"
    if not raw:
        return None
    try:
        prod = json.loads(raw)
    except Exception:
        return None
    if not isinstance(prod, dict) or not prod.get("dataFolderName"):
        return None
    cli = None
    app_name = prod.get("applicationName")
    for cand in (res / "app" / "bin" / str(app_name), res / "bin" / str(app_name)):
        if app_name and cand.exists():
            cli = str(cand.relative_to(app))
    return {"source": src, "name": prod.get("nameShort") or prod.get("nameLong"),
            "version": prod.get("version"), "data_folder": prod.get("dataFolderName"),
            "application_name": app_name, "cli": cli,
            "gallery": bool(prod.get("extensionsGallery"))}


def find_tools(app: Path, info: dict) -> tuple[list[str], list[str]]:
    """(the app's own CLIs, other bundled executables). A CLI counts as the app's own when it
    is named `cli` or after the app; the rest (a bundled git, an encoder) are not interfaces."""
    c = app / "Contents"
    main = info.get("CFBundleExecutable") or ""
    main_real = (c / "MacOS" / main).resolve() if main else None
    own_names = {"cli", main.lower(), str(info.get("CFBundleName", "")).lower()}
    clis: list[str] = []
    other: list[str] = []
    for d in ("MacOS", "Resources/app/bin", "Resources/bin"):
        for n in listdir(c / d):
            p = c / d / n
            if n.startswith(".") or n == main or not p.is_file() or (main_real and p.resolve() == main_real):
                continue
            (clis if n.lower() in own_names else other).append(f"Contents/{d}/{n}")
    return clis, other


def state_locations(app: Path, info: dict, home: Path, vsc: dict | None) -> list[dict]:
    bid = info.get("CFBundleIdentifier") or ""
    names = []
    for k in ("CFBundleName", "CFBundleDisplayName"):
        v = info.get(k)
        if v and v not in names:
            names.append(v)
    lib = home / "Library"
    cands: list[tuple[str, Path]] = []
    for n in names + ([bid] if bid else []):
        cands.append(("app-support", lib / "Application Support" / n))
    for n in names:
        lower = n.lower()
        if lower != n:
            cands.append(("app-support", lib / "Application Support" / lower))
    if bid:
        cands.append(("container", lib / "Containers" / bid))
        cands.append(("preferences", lib / "Preferences" / f"{bid}.plist"))
    if vsc and vsc.get("data_folder"):
        cands.append(("extensions", home / vsc["data_folder"] / "extensions"))
    seen: set[str] = set()
    out = []
    for kind, p in cands:
        key = str(p).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"kind": kind, "path": tilde(p, home), "exists": p.exists()})
    return out


def code_outside_bundle(home: Path, state: list[dict]) -> list[str]:
    """App-code archives kept in the state folder (an app that updates its own code)."""
    found = []
    for s in state:
        if s["kind"] != "app-support" or not s["exists"]:
            continue
        real = Path(s["path"].replace("~", str(home), 1))
        for n in listdir(real):
            if n.endswith(".asar"):
                found.append(f"{s['path']}/{n}")
    return found


def extension_points(app: Path, info: dict, vsc: dict | None, clis: list[str]) -> list[dict]:
    c = app / "Contents"
    out: list[dict] = []
    bid = info.get("CFBundleIdentifier") or ""
    for k in KNOWN_APIS.get(bid, []):
        out.append({**k, "source": "known (checked against this app; not advertised by the bundle)"})
    if vsc:
        out.append({"rung": "2", "kind": "vscode-extensions", "name": f"{vsc['name']} extension API",
                    "detail": f"product.json at {vsc['source']}; per-user folder ~/{vsc['data_folder']}"
                              + (f"; CLI {vsc['cli']} takes --user-data-dir and --extensions-dir" if vsc["cli"] else ""),
                    "source": "bundle"})
    sdef = info.get("OSAScriptingDefinition")
    if sdef and (c / "Resources" / sdef).exists():
        out.append({"rung": "2", "kind": "applescript", "name": "AppleScript dictionary",
                    "detail": f"Contents/Resources/{sdef}", "source": "bundle"})
    elif info.get("NSAppleScriptEnabled"):
        out.append({"rung": "2", "kind": "applescript", "name": "AppleScript (standard suite only)",
                    "detail": "NSAppleScriptEnabled with no .sdef", "source": "bundle"})
    if (c / "Resources" / "Metadata.appintents").exists():
        out.append({"rung": "2", "kind": "app-intents", "name": "App Intents (Shortcuts actions)",
                    "detail": "Contents/Resources/Metadata.appintents", "source": "bundle"})
    for cli in clis:
        if vsc and vsc.get("cli") == cli:
            continue
        out.append({"rung": "2", "kind": "cli", "name": "bundled command-line tool",
                    "detail": cli, "source": "bundle"})
    schemes = [s for t in info.get("CFBundleURLTypes", []) or [] if isinstance(t, dict)
               for s in t.get("CFBundleURLSchemes", []) or []]
    # OAuth redirect schemes (reversed client ids) are not an interface for us.
    schemes = [s for s in schemes if not s.startswith("com.googleusercontent.apps.")]
    if schemes:
        out.append({"rung": "2", "kind": "url-scheme", "name": "URL schemes",
                    "detail": ", ".join(f"{s}://" for s in schemes), "source": "bundle"})
    services = [s.get("NSMenuItem", {}).get("default") for s in info.get("NSServices", []) or []
                if isinstance(s, dict)]
    if services:
        out.append({"rung": "2", "kind": "services", "name": "Services menu items",
                    "detail": ", ".join(x for x in services if x), "source": "bundle"})
    out.append({"rung": "2", "kind": "accessibility", "name": "Accessibility (AX) API",
                "detail": "every app; needs the Accessibility permission, reads and drives the UI",
                "source": "platform"})
    return out


def protections(app: Path, sig: dict, fz: dict | None) -> dict:
    c = app / "Contents"
    p: dict = {"signature": sig, "mas_receipt": (c / "_MASReceipt").exists()}
    if fz and fz.get("found"):
        f = fz["fuses"]
        p["asar_integrity"] = f.get("EnableEmbeddedAsarIntegrityValidation") == "on"
        p["only_load_app_from_asar"] = f.get("OnlyLoadAppFromAsar") == "on"
        p["node_inspect"] = f.get("EnableNodeCliInspectArguments") == "on"
        p["node_options"] = f.get("EnableNodeOptionsEnvironmentVariable") == "on"
        p["run_as_node"] = f.get("RunAsNode") == "on"
    return p


def update_channels(app: Path, info: dict, frameworks: list[str], outside: list[str]) -> list[dict]:
    c = app / "Contents"
    out = []
    if "Sparkle.framework" in frameworks:
        out.append({"kind": "sparkle", "detail": info.get("SUFeedURL") or "feed set at runtime"})
    if "Squirrel.framework" in frameworks:
        out.append({"kind": "squirrel", "detail": "Electron autoUpdater (replaces the bundle)"})
    if (c / "Resources" / "app-update.yml").exists():
        out.append({"kind": "electron-updater", "detail": "Contents/Resources/app-update.yml"})
    if (c / "_MASReceipt").exists():
        out.append({"kind": "mac-app-store", "detail": "Contents/_MASReceipt"})
    if outside:
        out.append({"kind": "app-code-in-state-folder", "detail": ", ".join(outside)})
    return out


def rank_routes(facts: dict) -> list[dict]:
    st = facts["stack"]["kind"]
    prot = facts["protections"]
    sig = prot["signature"]
    sandboxed = bool(sig.get("sandbox")) or prot["mas_receipt"]
    eps = facts["extension_points"]
    routes: list[dict] = []

    # Rung 1: what the app already reads.
    existing = [s["path"] for s in facts["state"] if s["exists"]]
    r1 = [e for e in eps if e["rung"] == "1"]
    if r1:
        for e in r1:
            routes.append({"rung": "1", "name": e["name"], "status": "available",
                           "reason": f"the app reads it with no code of ours: {e['detail']}"})
    else:
        where = ", ".join(existing) if existing else "no state folder found yet (run the app once in a lab)"
        routes.append({"rung": "1", "name": "settings and data files", "status": "available",
                       "reason": "cheapest, but reaches only what the app already reads; state: " + where
                                 + ("; sandboxed, so state lives in its container" if sandboxed else "")})

    # Rung 2: sanctioned interfaces, most capable first.
    r2 = sorted((e for e in eps if e["rung"] == "2"), key=lambda e: RUNG2_ORDER.index(e["kind"])
                if e["kind"] in RUNG2_ORDER else len(RUNG2_ORDER))
    for e in r2:
        status, reason = "available", ""
        if e["kind"] in ("plugin-api", "vscode-extensions"):
            reason = "the makers' extension point: can add UI and behaviour; " + e["detail"]
        elif e["kind"] == "applescript":
            reason = "drive the app from osascript within its dictionary; cannot add UI"
        elif e["kind"] == "app-intents":
            reason = "Shortcuts actions the app exposes; cannot add UI"
        elif e["kind"] == "cli":
            reason = f"run the app's own tool ({e['detail']}); check --help for lab flags"
        elif e["kind"] == "url-scheme":
            reason = (f"deep links ({e['detail']}); trigger only. Caveat: `open` routes to an "
                      "already-running instance, which may be the user's real profile")
            status = "caveat"
        elif e["kind"] == "services":
            reason = "Services menu actions; trigger only"
        elif e["kind"] == "accessibility":
            reason = ("read and drive the UI; needs the Accessibility permission and acting "
                      "through it is driving input, so ask first")
            status = "caveat"
            if st in ("electron", "cef", "flutter"):
                reason += f"; the {st} UI exposes a thin AX tree"
        routes.append({"rung": "2", "name": e["name"], "status": status, "reason": reason})

    # Rung 3: code in-process.
    if st in ("electron", "cef"):
        terms = "check the app's terms first: a prohibition on client modification puts this out of scope"
        reason = ("launch-time renderer script over the DevTools Protocol "
                  "(--remote-debugging-port, lab profile, session only); app files untouched; " + terms)
        if prot.get("node_inspect") is False:
            reason += "; the Node inspect fuse is off (the main process is closed; the renderer port is a different door)"
        routes.append({"rung": "3", "name": "renderer script via DevTools Protocol",
                       "status": "caveat", "reason": reason})
    elif sig.get("checked") and sig.get("signed") and not sig.get("disable_library_validation") \
            and sig.get("hardened_runtime"):
        routes.append({"rung": "3", "name": "in-process code (dylib)", "status": "blocked",
                       "reason": "hardened runtime with library validation: injecting means defeating a protection"})
    else:
        routes.append({"rung": "3", "name": "in-process code (dylib)", "status": "caveat",
                       "reason": "library validation is off or unknown, but injection is fragile and "
                                 "rarely within the terms; prefer rung 2"})
    edit_reason = "editing a signed bundle breaks its seal: that defeats an integrity check"
    if prot.get("asar_integrity"):
        edit_reason += "; the asar integrity fuse is on as well"
    if any(u["kind"] in ("sparkle", "squirrel", "electron-updater", "mac-app-store") for u in facts["updates"]):
        edit_reason += "; an updater would overwrite the edit anyway"
    if sig.get("checked") and sig.get("signed") is False:
        routes.append({"rung": "3", "name": "edit the app's files", "status": "caveat",
                       "reason": "the bundle is unsigned, but an in-place edit is lost on update; back up first"})
    else:
        routes.append({"rung": "3", "name": "edit the app's files", "status": "blocked",
                       "reason": edit_reason})

    # Rung 4 and 5.
    routes.append({"rung": "4", "name": "network capture of the app's own traffic", "status": "caveat",
                   "reason": "your own account and data only; rarely needed for an app mod"})
    routes.append({"rung": "5", "name": "companion tool beside the app", "status": "available",
                   "reason": "rebuild the part you need next to the app, from its data files or API; "
                             "most work, and the user sees it outside the app"})

    # The ladder's order: cheapest rung first; inside a rung, available before caveat; blocked
    # routes go last whatever their rung, so the list reads as "try these, in this order".
    ranked = sorted(enumerate(routes), key=lambda ir: (ir[1]["status"] == "blocked", int(ir[1]["rung"]),
                                                         STATUS_ORDER[ir[1]["status"]], ir[0]))
    return [dict(r, rank=i + 1) for i, (_, r) in enumerate(ranked)]


def recon(target: str, arch: str | None = None, runner: Runner | None = None,
          home: Path | None = None) -> dict:
    home = home or Path.home()
    arch = arch or ("arm64" if platform.machine() in ("arm64", "aarch64") else "x86_64")
    app = resolve_target(target, home)
    c = app / "Contents"
    info = read_plist(c / "Info.plist")
    frameworks = listdir(c / "Frameworks")
    stack = detect_stack(app, info, frameworks)
    fz = None
    if stack["kind"] == "electron":
        stack["electron"] = electron_facts(app, arch)
        fz = stack["electron"].get("fuse_wire")
    vsc = vscode_family(app)
    if vsc:
        stack["vscode_family"] = vsc
    clis, other_tools = find_tools(app, info)
    state = state_locations(app, info, home, vsc)
    outside = code_outside_bundle(home, state)
    sig = read_signature(app, runner)
    facts = {
        "target": {
            "path": tilde(app, home),
            "name": info.get("CFBundleName") or app.stem,
            "bundle_id": info.get("CFBundleIdentifier"),
            "version": info.get("CFBundleShortVersionString"),
            "build": info.get("CFBundleVersion"),
            "min_os": info.get("LSMinimumSystemVersion"),
            "arch": arch,
        },
        "stack": stack,
        "extension_points": extension_points(app, info, vsc, clis),
        "protections": protections(app, sig, fz),
        "updates": update_channels(app, info, frameworks, outside),
        "state": state,
        "app_extensions": [n for n in listdir(c / "PlugIns") if n.endswith(".appex")],
        "bundled_tools": other_tools,
    }
    caveats = []
    if outside:
        caveats.append("Info.plist says version {} but the state folder holds app-code archives ({}); "
                       "the running version may be the newest of those".format(
                           facts["target"]["version"], ", ".join(Path(o).name for o in outside)))
    if fz and fz.get("found") and not fz.get("slices_agree", True):
        caveats.append("the fuse wires differ between slices; the {} slice is the one reported".format(fz["slice"]))
    if vsc and vsc.get("version") and vsc["version"] != facts["target"]["version"]:
        caveats.append(f"product.json version {vsc['version']} differs from Info.plist {facts['target']['version']}")
    facts["caveats"] = caveats
    facts["routes"] = rank_routes(facts)
    return facts


def render_text(f: dict) -> str:
    t = f["target"]
    lines = [f"{t['name']} {t['version']} ({t['bundle_id']}) at {t['path']}",
             f"stack: {f['stack']['kind']}"]
    el = f["stack"].get("electron")
    if el:
        fw = el.get("fuse_wire") or {}
        on = [k for k, v in (fw.get("fuses") or {}).items() if v == "on"]
        lines.append(f"  electron {el.get('electron_version', '?')}; code: {', '.join(el['app_code']) or '-'}; "
                     f"fuses on ({fw.get('slice', '?')}): {', '.join(on) or 'none'}")
    sig = f["protections"]["signature"]
    if sig.get("checked"):
        lines.append(f"signature: team {sig.get('team_id')}, hardened runtime {sig.get('hardened_runtime')}, "
                     f"sandbox {sig.get('sandbox')}")
    lines.append("updates: " + (", ".join(u["kind"] for u in f["updates"]) or "none detected"))
    lines.append("extension points:")
    lines += [f"  rung {e['rung']} {e['kind']}: {e['name']} — {e['detail']}" for e in f["extension_points"]]
    lines.append("state: " + (", ".join(s["path"] for s in f["state"] if s["exists"]) or "none found"))
    for c in f["caveats"]:
        lines.append(f"caveat: {c}")
    lines.append("routes (cheapest available first):")
    lines += [f"  {r['rank']}. rung {r['rung']} [{r['status']}] {r['name']} — {r['reason']}" for r in f["routes"]]
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="recon_macos_app.py", description=__doc__.split("\n")[0])
    ap.add_argument("target", help="path to Foo.app, or a bare app name in /Applications")
    ap.add_argument("--json", action="store_true", help="print the facts and routes as JSON")
    ap.add_argument("--arch", choices=sorted(CPU_TYPES), help="slice to read fuses from (default: this machine)")
    ap.add_argument("--no-codesign", action="store_true", help="skip the codesign probe")
    ap.add_argument("--home", help="home folder for state lookups (default: the real home; tests use a tmp dir)")
    ns = ap.parse_args(argv)
    runner = None if ns.no_codesign or not shutil.which("codesign") else default_runner
    try:
        facts = recon(ns.target, ns.arch, runner, Path(ns.home) if ns.home else None)
    except NotABundle as e:
        print(f"refused: {e}", file=sys.stderr)
        return 2
    print(json.dumps(facts, indent=2) if ns.json else render_text(facts))
    return 0


if __name__ == "__main__":
    sys.exit(main())
