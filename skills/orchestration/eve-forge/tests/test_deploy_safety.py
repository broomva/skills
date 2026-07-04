import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))
import deploy_safety as ds  # noqa: E402


# --- happy path ---
def test_vercel_oidc_passes_prod():
    ok, reason = ds.assess_auth("auth: [vercelOidc(), localDev()]")
    assert ok and "vercelOidc" in reason


def test_none_allowed_in_dev():
    ok, _ = ds.assess_auth("auth: [none()]", env="dev")
    assert ok


def test_missing_auth_fail_closed():
    ok, reason = ds.assess_auth("export default { channel: 'eve' }")
    assert not ok and "fail-closed" in reason


def test_lone_localdev_blocked_prod():
    ok, reason = ds.assess_auth("auth: [localDev()]")
    assert not ok and "no verifiable real authenticator" in reason


def test_placeholder_blocked_in_prod():
    ok, _ = ds.assess_auth("auth: [placeholderAuth()]")
    assert not ok


# --- P20 fail-OPEN regression tests (each MUST now block) ---
def test_p20_nested_options_array_none_blocked():
    # #1: inner options array `["a"]` must not truncate the parse before none()
    ok, reason = ds.assess_auth('auth: [jwt({ audience: ["a"] }), none()]')
    assert not ok and "unsafe" in reason


def test_p20_multiple_channels_second_unsafe_blocked():
    # #2: a safe channel written first must not mask an unsafe one
    ok, _ = ds.assess_auth(
        "export default [ {channel:'admin', auth:[vercelOidc()]}, {channel:'public', auth:[none()]} ]"
    )
    assert not ok


def test_p20_commented_safe_then_live_unsafe_blocked():
    # #3: a commented-out safe array must not shadow the live none()
    ok, _ = ds.assess_auth("// auth: [vercelOidc()]\nauth: [none()]")
    assert not ok


def test_p20_tsx_channel_scanned(tmp_path):
    # #4: non-.ts channel files must be scanned
    ch = tmp_path / "channels"
    ch.mkdir()
    (ch / "main.ts").write_text("auth: [vercelOidc()]")
    (ch / "public.tsx").write_text("auth: [none()]")
    ok, rows = ds.scan_dir(str(tmp_path))
    assert not ok and any(r[0].endswith("public.tsx") and not r[1] for r in rows)


# --- P20 false-BLOCK fixes (each MUST now pass) ---
def test_custom_authenticator_passes():
    ok, _ = ds.assess_auth("auth: [clerkAuth()]")
    assert ok


def test_description_string_not_falsely_blocked():
    ok, _ = ds.assess_auth('const d = "auth: [none()]";\nexport default { auth: [vercelOidc()] }')
    assert ok


def test_variable_auth_fails_closed():
    # known limitation, fail-SAFE: variable-defined auth can't be verified -> block
    ok, reason = ds.assess_auth("const a = vercelOidc();\nexport default { auth: [a] }")
    assert not ok and "no verifiable real authenticator" in reason


def test_scan_dir_no_channels_fails(tmp_path):
    ok, rows = ds.scan_dir(str(tmp_path))
    assert not ok and rows[0][0] == "<none>"


def test_scan_dir_ignores_node_modules(tmp_path):
    # BRO-1685: a project-root scan must not fail on the eve library's own
    # channel files under node_modules/eve/dist/**/channels/*.ts.
    ch = tmp_path / "channels"
    ch.mkdir()
    (ch / "eve.ts").write_text("auth: [vercelOidc()]")
    nm = tmp_path / "node_modules" / "eve" / "dist" / "channels"
    nm.mkdir(parents=True)
    (nm / "x.ts").write_text("auth: [none()]")  # library file — must be skipped
    ok, rows = ds.scan_dir(str(tmp_path))
    assert ok and all("node_modules" not in r[0] for r in rows)
