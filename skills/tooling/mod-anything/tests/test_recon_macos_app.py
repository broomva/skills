"""Tests for scripts/recon_macos_app.py — facts and ranked routes for a macOS app bundle.

Every bundle here is a fake built in a tmp dir: the tests never read /Applications and never
run the real codesign (a fake runner stands in), so they pass on any OS.
"""
from __future__ import annotations

import importlib.util
import json
import plistlib
import struct
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "recon_macos_app.py"
spec = importlib.util.spec_from_file_location("recon_macos_app", SCRIPT)
rma = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rma)

ON, OFF, REMOVED = 0x31, 0x30, 0x72


# ---------------------------------------------------------------- builders

def make_app(root: Path, name: str = "Fake", info: dict | None = None) -> Path:
    app = root / f"{name}.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    (app / "Contents" / "Resources").mkdir()
    (app / "Contents" / "Frameworks").mkdir()
    base = {"CFBundleIdentifier": f"test.{name.lower()}", "CFBundleName": name,
            "CFBundleShortVersionString": "1.2.3", "CFBundleVersion": "123",
            "CFBundleExecutable": name}
    base.update(info or {})
    with (app / "Contents" / "Info.plist").open("wb") as f:
        plistlib.dump(base, f)
    (app / "Contents" / "MacOS" / name).write_bytes(b"\xcf\xfa\xed\xfe")
    return app


def wire(*states: int) -> bytes:
    return rma.FUSE_SENTINEL + bytes([1, len(states)]) + bytes(states)


def thin(cpu: int, payload: bytes) -> bytes:
    return b"\xcf\xfa\xed\xfe" + struct.pack("<I", cpu) + b"\x00" * 24 + payload + b"\x00" * 16


def fat(slices: list[tuple[int, bytes]]) -> bytes:
    """A universal binary: fat header, then each slice at a 4 KiB-aligned offset."""
    header = b"\xca\xfe\xba\xbe" + struct.pack(">I", len(slices))
    offset = 4096
    body = b""
    for cpu, data in slices:
        header += struct.pack(">IIIII", cpu, 0, offset, len(data), 12)
        body += data + b"\x00" * (4096 - len(data) % 4096)
        offset += len(data) + (4096 - len(data) % 4096)
    return header + b"\x00" * (4096 - len(header)) + body


def make_electron(app: Path, binary: bytes, version: str = "33.3.2") -> Path:
    fw = app / "Contents" / "Frameworks" / "Electron Framework.framework"
    (fw / "Resources").mkdir(parents=True)
    (fw / "Electron Framework").write_bytes(binary)
    with (fw / "Resources" / "Info.plist").open("wb") as f:
        plistlib.dump({"CFBundleVersion": version}, f)
    return fw


def make_asar(path: Path, files: dict[str, bytes]) -> None:
    """The asar layout: a pickle (u32 size, u32 header size), then the header pickle
    (u32 payload size, u32 json length, json, padding), then the file bytes."""
    index, offset, blob = {}, 0, b""
    for name, data in files.items():
        index[name] = {"size": len(data), "offset": str(offset)}
        offset += len(data)
        blob += data
    js = json.dumps({"files": index}).encode()
    pad = (4 - len(js) % 4) % 4
    header_pickle = struct.pack("<II", 4 + len(js) + pad, len(js)) + js + b"\x00" * pad
    path.write_bytes(struct.pack("<II", 4, len(header_pickle)) + header_pickle + blob)


def fake_codesign(*, signed=True, runtime=True, team="ABCDE12345", entitlements=None):
    ents = entitlements or {}

    def runner(cmd: list[str]) -> subprocess.CompletedProcess:
        if "--entitlements" in cmd:
            out = plistlib.dumps(ents).decode() if signed else ""
            return subprocess.CompletedProcess(cmd, 0 if signed else 1, out, "")
        if not signed:
            return subprocess.CompletedProcess(cmd, 1, "", f"{cmd[-1]}: code object is not signed at all")
        flags = "0x10000(runtime)" if runtime else "0x0(none)"
        err = f"Executable=x\nCodeDirectory v=20500 size=1 flags={flags} hashes=1+7\nTeamIdentifier={team}\n"
        return subprocess.CompletedProcess(cmd, 0, "", err)

    return runner


def run_cli(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


@pytest.fixture
def home(tmp_path: Path) -> Path:
    h = tmp_path / "home"
    h.mkdir()
    return h


def routes_by_name(facts: dict) -> dict[str, dict]:
    return {r["name"]: r for r in facts["routes"]}


# ---------------------------------------------------------------- fuses

def test_fuse_wire_decodes_on_off_removed(tmp_path: Path):
    b = tmp_path / "bin"
    b.write_bytes(thin(rma.CPU_TYPES["arm64"], wire(OFF, ON, REMOVED, OFF, ON, ON, OFF, ON, OFF)))
    fz = rma.read_fuses(b, "arm64")
    assert fz["found"] and fz["slice"] == "arm64" and fz["count"] == 9
    assert fz["fuses"]["RunAsNode"] == "off"
    assert fz["fuses"]["EnableCookieEncryption"] == "on"
    assert fz["fuses"]["EnableNodeOptionsEnvironmentVariable"] == "removed"
    assert fz["fuses"]["EnableEmbeddedAsarIntegrityValidation"] == "on"


def test_universal_binary_reads_the_requested_slice_and_flags_disagreement(tmp_path: Path):
    b = tmp_path / "bin"
    x86 = wire(ON, OFF, ON, ON, OFF, OFF, OFF, ON)            # inspect on in the Intel slice
    arm = wire(OFF, OFF, OFF, OFF, ON, ON, OFF, ON)           # asar integrity on in the arm slice
    b.write_bytes(fat([(rma.CPU_TYPES["x86_64"], x86), (rma.CPU_TYPES["arm64"], arm)]))
    a = rma.read_fuses(b, "arm64")
    x = rma.read_fuses(b, "x86_64")
    assert a["slice"] == "arm64" and a["fuses"]["EnableEmbeddedAsarIntegrityValidation"] == "on"
    assert x["slice"] == "x86_64" and x["fuses"]["EnableNodeCliInspectArguments"] == "on"
    assert a["slices"] == ["arm64", "x86_64"] and a["slices_agree"] is False


def test_universal_binary_with_identical_wires_agrees(tmp_path: Path):
    b = tmp_path / "bin"
    w = wire(OFF, OFF, OFF, OFF, OFF, OFF, OFF, ON)
    b.write_bytes(fat([(rma.CPU_TYPES["x86_64"], w), (rma.CPU_TYPES["arm64"], w)]))
    assert rma.read_fuses(b, "arm64")["slices_agree"] is True


def test_binary_without_a_wire_reports_not_found(tmp_path: Path):
    b = tmp_path / "bin"
    b.write_bytes(thin(rma.CPU_TYPES["arm64"], b"no fuses here"))
    assert rma.read_fuses(b, "arm64") == {"found": False, "slice": "arm64"}


# ---------------------------------------------------------------- stacks and extension points

def test_electron_app_with_asar_integrity_blocks_file_edits(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Chat")
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(OFF, ON, OFF, OFF, ON, ON, OFF, ON)))
    make_asar(app / "Contents" / "Resources" / "app.asar", {"package.json": b"{}"})
    (app / "Contents" / "Frameworks" / "Squirrel.framework").mkdir()
    f = rma.recon(str(app), "arm64", fake_codesign(), home)
    assert f["stack"]["kind"] == "electron"
    assert f["stack"]["electron"]["electron_version"] == "33.3.2"
    assert f["stack"]["electron"]["app_code"] == ["Contents/Resources/app.asar"]
    assert f["protections"]["asar_integrity"] is True and f["protections"]["node_inspect"] is False
    r = routes_by_name(f)
    assert r["edit the app's files"]["status"] == "blocked"
    assert "asar integrity" in r["edit the app's files"]["reason"]
    assert r["renderer script via DevTools Protocol"]["status"] == "caveat"
    assert "terms" in r["renderer script via DevTools Protocol"]["reason"]
    assert {"kind": "squirrel", "detail": "Electron autoUpdater (replaces the bundle)"} in f["updates"]


def test_vscode_family_from_unpacked_product_json(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Code", {"CFBundleURLTypes": [{"CFBundleURLSchemes": ["vscode"]}]})
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(ON, OFF, ON, ON, OFF, OFF, OFF, ON)))
    appdir = app / "Contents" / "Resources" / "app"
    (appdir / "bin").mkdir(parents=True)
    (appdir / "bin" / "code").write_text("#!/bin/sh\n")
    (appdir / "product.json").write_text(json.dumps(
        {"nameShort": "Code", "version": "1.2.3", "dataFolderName": ".vscode",
         "applicationName": "code", "extensionsGallery": {"serviceUrl": "x"}}))
    f = rma.recon(str(app), "arm64", None, home)
    vsc = f["stack"]["vscode_family"]
    assert vsc["cli"] == "Contents/Resources/app/bin/code" and vsc["data_folder"] == ".vscode"
    top = [r for r in f["routes"] if r["rung"] == "2"][0]
    assert top["name"] == "Code extension API" and top["status"] == "available"
    # the app's own CLI is folded into the extension-API entry, not listed twice
    assert not any(e["kind"] == "cli" for e in f["extension_points"])
    assert {"kind": "extensions", "path": "~/.vscode/extensions", "exists": False} in f["state"]


def test_vscode_fork_with_product_json_inside_app_asar(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Fork", {"CFBundleShortVersionString": "2.0.0"})
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(OFF, OFF, OFF, OFF, OFF, OFF, OFF, OFF)))
    make_asar(app / "Contents" / "Resources" / "app.asar", {
        "package.json": b'{"name": "fork"}',
        "product.json": json.dumps({"nameShort": "Fork", "version": "1.107.0",
                                    "dataFolderName": ".fork", "applicationName": "fork"}).encode()})
    f = rma.recon(str(app), "arm64", None, home)
    assert f["stack"]["vscode_family"]["source"] == "Contents/Resources/app.asar:product.json"
    assert any("1.107.0 differs from Info.plist 2.0.0" in c for c in f["caveats"])


def test_known_api_table_puts_the_plugin_api_first_in_rung_2(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Obsidian", {"CFBundleIdentifier": "md.obsidian",
                                          "CFBundleURLTypes": [{"CFBundleURLSchemes": ["obsidian"]}]})
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(OFF, OFF, OFF, OFF, OFF, OFF, OFF, ON)))
    f = rma.recon(str(app), "arm64", None, home)
    rung2 = [r for r in f["routes"] if r["rung"] == "2"]
    assert rung2[0]["name"] == "Obsidian community plugin API"
    assert "restricted mode" in rung2[0]["reason"]
    assert f["routes"][0]["rung"] == "1" and "snippets" in f["routes"][0]["reason"]
    known = [e for e in f["extension_points"] if e["kind"] == "plugin-api"][0]
    assert known["source"].startswith("known")


def test_app_code_in_the_state_folder_is_a_version_caveat_with_tilde_paths(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Notes", {"CFBundleShortVersionString": "1.8.4"})
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(OFF, OFF, OFF, OFF, OFF, OFF, OFF, ON)))
    support = home / "Library" / "Application Support" / "Notes"
    support.mkdir(parents=True)
    (support / "notes-1.13.7.asar").write_bytes(b"x")
    f = rma.recon(str(app), "arm64", None, home)
    assert any("1.8.4" in c and "notes-1.13.7.asar" in c for c in f["caveats"])
    assert {"kind": "app-code-in-state-folder",
            "detail": "~/Library/Application Support/Notes/notes-1.13.7.asar"} in f["updates"]
    assert str(home) not in json.dumps(f)


def test_native_scriptable_app(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Term", {"OSAScriptingDefinition": "Term.sdef",
                                      "NSServices": [{"NSMenuItem": {"default": "New Term Here"}}]})
    (app / "Contents" / "Resources" / "Term.sdef").write_text("<dictionary/>")
    (app / "Contents" / "Resources" / "Metadata.appintents").mkdir()
    (app / "Contents" / "Frameworks" / "Sparkle.framework").mkdir()
    with (app / "Contents" / "Info.plist").open("rb") as fh:
        info = plistlib.load(fh)
    info["SUFeedURL"] = "https://example.invalid/appcast.xml"
    with (app / "Contents" / "Info.plist").open("wb") as fh:
        plistlib.dump(info, fh)
    f = rma.recon(str(app), "arm64", fake_codesign(), home)
    assert f["stack"]["kind"] == "native"
    kinds = [e["kind"] for e in f["extension_points"]]
    assert {"applescript", "app-intents", "services", "accessibility"} <= set(kinds)
    rung2 = [r["name"] for r in f["routes"] if r["rung"] == "2"]
    assert rung2.index("AppleScript dictionary") < rung2.index("App Intents (Shortcuts actions)")
    assert {"kind": "sparkle", "detail": "https://example.invalid/appcast.xml"} in f["updates"]
    r = routes_by_name(f)
    assert r["in-process code (dylib)"]["status"] == "blocked"


def test_applescript_enabled_without_sdef(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Plain", {"NSAppleScriptEnabled": True})
    f = rma.recon(str(app), "arm64", None, home)
    assert any(e["name"] == "AppleScript (standard suite only)" for e in f["extension_points"])


def test_library_validation_off_turns_dylib_route_into_a_caveat(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Loose")
    runner = fake_codesign(entitlements={"com.apple.security.cs.disable-library-validation": True})
    f = rma.recon(str(app), "arm64", runner, home)
    assert f["protections"]["signature"]["disable_library_validation"] is True
    assert routes_by_name(f)["in-process code (dylib)"]["status"] == "caveat"


def test_store_build_is_sandboxed_and_state_lives_in_its_container(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Writer", {"CFBundleIdentifier": "com.example.writer"})
    (app / "Contents" / "_MASReceipt").mkdir()
    (home / "Library" / "Containers" / "com.example.writer").mkdir(parents=True)
    runner = fake_codesign(entitlements={"com.apple.security.app-sandbox": True})
    f = rma.recon(str(app), "arm64", runner, home)
    assert f["protections"]["mas_receipt"] and f["protections"]["signature"]["sandbox"]
    assert f["updates"][0]["kind"] == "mac-app-store"
    first = f["routes"][0]
    assert first["rung"] == "1" and "container" in first["reason"]
    assert "~/Library/Containers/com.example.writer" in first["reason"]


def test_unsigned_bundle_makes_file_edit_a_caveat_not_a_block(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Homebrew")
    f = rma.recon(str(app), "arm64", fake_codesign(signed=False), home)
    assert f["protections"]["signature"] == {"checked": True, "signed": False,
                                             "detail": f"{app.name}: code object is not signed at all"}
    assert routes_by_name(f)["edit the app's files"]["status"] == "caveat"


@pytest.mark.parametrize("framework,kind", [
    ("Chromium Embedded Framework.framework", "cef"),
    ("FlutterMacOS.framework", "flutter"),
    ("QtCore.framework", "qt"),
])
def test_stack_detection(tmp_path: Path, home: Path, framework: str, kind: str):
    app = make_app(tmp_path, "S")
    (app / "Contents" / "Frameworks" / framework).mkdir()
    f = rma.recon(str(app), "arm64", None, home)
    assert f["stack"]["kind"] == kind
    has_cdp = any(r["name"] == "renderer script via DevTools Protocol" for r in f["routes"])
    assert has_cdp == (kind == "cef")


def test_oauth_redirect_schemes_are_not_listed(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "N", {"CFBundleURLTypes": [
        {"CFBundleURLSchemes": ["com.googleusercontent.apps.123-abc", "notes"]}]})
    f = rma.recon(str(app), "arm64", None, home)
    ep = [e for e in f["extension_points"] if e["kind"] == "url-scheme"][0]
    assert ep["detail"] == "notes://"


def test_own_cli_is_a_route_but_a_bundled_git_is_not(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Ed")
    macos = app / "Contents" / "MacOS"
    (macos / "cli").write_bytes(b"x")
    (macos / "git").write_bytes(b"x")
    (macos / "Electron").symlink_to("Ed")
    f = rma.recon(str(app), "arm64", None, home)
    clis = [e["detail"] for e in f["extension_points"] if e["kind"] == "cli"]
    assert clis == ["Contents/MacOS/cli"]
    assert f["bundled_tools"] == ["Contents/MacOS/git"]


# ---------------------------------------------------------------- ranking invariants

def test_ranking_follows_the_ladder_and_puts_blocked_last(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Chat", {"CFBundleURLTypes": [{"CFBundleURLSchemes": ["chat"]}]})
    make_electron(app, thin(rma.CPU_TYPES["arm64"], wire(OFF, ON, OFF, OFF, ON, ON, OFF, ON)))
    f = rma.recon(str(app), "arm64", fake_codesign(), home)
    rs = f["routes"]
    assert [r["rank"] for r in rs] == list(range(1, len(rs) + 1))
    open_ = [r for r in rs if r["status"] != "blocked"]
    assert [int(r["rung"]) for r in open_] == sorted(int(r["rung"]) for r in open_)
    assert all(r["status"] == "blocked" for r in rs[len(open_):])
    assert all(r["reason"] for r in rs)


# ---------------------------------------------------------------- CLI

def test_cli_json_and_text_and_no_codesign(tmp_path: Path, home: Path):
    app = make_app(tmp_path, "Cli")
    r = run_cli(str(app), "--json", "--no-codesign", "--home", str(home))
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert d["target"]["bundle_id"] == "test.cli" and d["target"]["version"] == "1.2.3"
    assert d["protections"]["signature"]["checked"] is False
    t = run_cli(str(app), "--no-codesign", "--home", str(home))
    assert t.returncode == 0 and "routes (cheapest available first):" in t.stdout


def test_bare_name_resolves_under_home_applications(tmp_path: Path, home: Path):
    make_app(home / "Applications", "ZzModAnythingFake")
    r = run_cli("ZzModAnythingFake", "--json", "--no-codesign", "--home", str(home))
    assert r.returncode == 0, r.stderr
    assert json.loads(r.stdout)["target"]["path"] == "~/Applications/ZzModAnythingFake.app"


def test_not_a_bundle_exits_2(tmp_path: Path):
    (tmp_path / "Empty.app").mkdir()
    r = run_cli(str(tmp_path / "Empty.app"), "--no-codesign")
    assert r.returncode == 2 and "not an app bundle" in r.stderr
    assert run_cli("NoSuchAppAnywhere-xyz", "--no-codesign", "--home", str(tmp_path)).returncode == 2
