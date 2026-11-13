"""Tests for sim_audit.py.

Each test copies the shipped example package (a falling body) into a temp
directory, breaks one thing, and checks that the audit names it. The package's
commands run with the interpreter running these tests.

`run_mutants.py` beside this file changes sim_audit.py one behaviour at a time
and requires these tests to fail each time.
"""

from __future__ import annotations

import copy
import json
import os
import shutil
import sys
import time
from pathlib import Path

import pytest
import yaml

SKILL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL / "scripts"))

import sim_audit  # noqa: E402
from sim_audit import FAIL, PASS, SKIP, WARN  # noqa: E402

EXAMPLE = SKILL / "assets" / "example" / "falling-body"
PY = sys.executable
TABLE = "test/table.test.py"


def with_interpreter(text: str) -> str:
    return text.replace("python3 ", f"{PY} ")


def example_ledger() -> dict:
    data = yaml.safe_load((EXAMPLE / "sim-claims.yaml").read_text(encoding="utf-8"))
    data["commands"] = {k: with_interpreter(v) for k, v in data["commands"].items()}
    for entry in data["mutations"]:
        entry["command"] = with_interpreter(entry["command"])
    return data


LEDGER = example_ledger()


def ledger() -> dict:
    return copy.deepcopy(LEDGER)


def claim(data: dict, cid: str) -> dict:
    return next(c for c in data["claims"] if c["id"] == cid)


def mutation(data: dict, mid: str) -> dict:
    return next(m for m in data["mutations"] if m["id"] == mid)


def build(root: Path, data: dict | None = None, **files: str) -> Path:
    """The example package under `root`, with a JSON ledger and `files` overlaid."""
    package = root / "pkg"
    shutil.copytree(EXAMPLE, package)
    (package / "sim-claims.yaml").unlink()
    for name, text in files.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (package / "sim-claims.json").write_text(
        json.dumps(ledger() if data is None else data), encoding="utf-8"
    )
    return package


def read(name: str) -> str:
    return (EXAMPLE / name).read_text(encoding="utf-8")


def statuses(audit: sim_audit.Audit, check: str) -> list[str]:
    return [r.status for r in audit.results if r.check == check]


def details(audit: sim_audit.Audit, check: str, status: str | None = None) -> str:
    return " | ".join(
        f"{r.subject}: {r.detail}"
        for r in audit.results
        if r.check == check and status in (None, r.status)
    )


def failures(audit: sim_audit.Audit, check: str) -> str:
    return details(audit, check, FAIL)


def passes(audit: sim_audit.Audit, check: str) -> str:
    return details(audit, check, PASS)


def full(package: Path, timeout: int = 60) -> sim_audit.Audit:
    return sim_audit.audit_package(package, run_report=True, run_mutations=True, timeout=timeout)


def static(package: Path) -> sim_audit.Audit:
    return sim_audit.audit_package(package)


def snapshot(package: Path) -> dict:
    return {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}


# The shipped example


def test_the_shipped_example_passes_strictly_from_its_yaml_ledger(tmp_path):
    package = tmp_path / "falling-body"
    shutil.copytree(EXAMPLE, package)
    text = (package / "sim-claims.yaml").read_text(encoding="utf-8")
    (package / "sim-claims.yaml").write_text(with_interpreter(text), encoding="utf-8")
    audit = full(package)
    assert not audit.failed(strict=True), sim_audit.render(audit, True)
    assert {r.status for r in audit.results} == {PASS}
    assert {c["kind"] for c in LEDGER["claims"]} == set(sim_audit.KINDS)


def test_each_example_mutation_is_killed_by_its_own_claims_test(tmp_path):
    for entry in LEDGER["mutations"]:
        assert claim(LEDGER, entry["claim"])["test"] in entry["command"], entry["id"]
    assert len({m["command"] for m in LEDGER["mutations"]}) == len(LEDGER["mutations"])


def test_every_check_reports(tmp_path):
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": f"{PY} tools/gate.py"}]
    package = build(tmp_path, data, **{"tools/gate.py": "assert True\n"})
    audit = sim_audit.audit_package(package, run_report=True, run_mutations=True, run_gates=True)
    assert {r.check for r in audit.results} == {
        "ledger", "asserting", "claims", "references", "coverage",
        "quoted", "suite", "gates", "mutations",
    }  # fmt: skip
    assert not audit.failed(strict=False)


def test_the_defaults_find_the_tests_the_docs_and_the_links(tmp_path):
    data = ledger()
    del data["tests"], data["docs"], data["link"]
    probe = read(TABLE) + "\nimport os\nassert os.path.islink('node_modules')\n"
    probe += "assert os.path.islink('target') and os.path.islink('.venv') and os.path.islink('venv')\n"
    files = {TABLE: probe}
    for name in ("node_modules", "target", ".venv", "venv"):
        files[f"{name}/x.txt"] = "x"
    audit = full(build(tmp_path, data, **files))
    assert "4 test files, each with an assertion" in passes(audit, "asserting")
    assert "2 quoted values appear in the docs" in passes(audit, "quoted")
    assert statuses(audit, "suite") == [PASS]


# The command line


def test_exit_codes(tmp_path, capsys):
    package = build(tmp_path)
    assert sim_audit.main([str(package), "--run-report", "--run-mutations"]) == 0
    capsys.readouterr()
    assert sim_audit.main([str(tmp_path / "missing")]) == 2
    out = capsys.readouterr()
    assert out.out == "" and "is not a directory" in out.err
    (tmp_path / "empty").mkdir()
    assert sim_audit.main([str(tmp_path / "empty")]) == 2
    data = ledger()
    data["claims"] = [c for c in data["claims"] if c["kind"] != "control"]
    data["mutations"] = [m for m in data["mutations"] if m["claim"] != "zero-height"]
    assert sim_audit.main([str(build(tmp_path / "bad", data))]) == 1
    capsys.readouterr()


def test_strict_fails_on_a_warning_and_on_a_skip(tmp_path, capsys):
    data = ledger()
    data["mutations"] = [m for m in data["mutations"] if m["claim"] != "energy"]
    warned = build(tmp_path / "warned", data)
    flags = ["--run-report", "--run-mutations"]
    assert sim_audit.main([str(warned), *flags]) == 0
    assert sim_audit.main([str(warned), *flags, "--strict"]) == 1
    clean = build(tmp_path / "clean")
    assert sim_audit.main([str(clean), *flags, "--strict"]) == 0
    assert sim_audit.main([str(clean)]) == 0
    assert sim_audit.main([str(clean), "--strict"]) == 1
    assert "strict: warnings and skips fail" in capsys.readouterr().out


def test_json_output_reports_failure(tmp_path, capsys):
    package = build(tmp_path)
    assert sim_audit.main([str(package), "--json", "--run-mutations"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {r["check"] for r in payload["results"]} >= {"ledger", "asserting", "mutations"}
    killed = [r for r in payload["results"] if r["subject"] == "weaker-gravity"]
    assert [r["status"] for r in killed] == [PASS] and "killed" in killed[0]["detail"]

    assert sim_audit.main([str(package), "--json", "--strict"]) == 1
    assert json.loads(capsys.readouterr().out)["ok"] is False

    (package / "README.md").write_text("Nothing quoted.\n", encoding="utf-8")
    assert sim_audit.main([str(package), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert any(r["status"] == FAIL and r["check"] == "quoted" for r in payload["results"])


def test_json_output_for_an_unreadable_ledger(tmp_path, capsys):
    package = build(tmp_path)
    (package / "sim-claims.json").write_text("{not json", encoding="utf-8")
    assert sim_audit.main([str(package), "--json"]) == 2
    out = capsys.readouterr()
    payload = json.loads(out.out)
    assert payload["ok"] is False and "sim-claims.json" in payload["error"]
    assert "sim-audit:" in out.err


@pytest.mark.parametrize(
    ("flag", "name", "check"),
    [
        ("--run-tests", TABLE, "suite"),
        ("--run-report", "tools/report.py", "quoted"),
        ("--run-gates", "tools/gate.py", "gates"),
    ],
)
def test_the_timeout_flag_reaches_every_command(tmp_path, capsys, flag, name, check):
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": f"{PY} tools/gate.py"}]
    files = {"tools/gate.py": "assert True\n"}
    files[name] = "import time\ntime.sleep(8)\n" + (read(name) if name != "tools/gate.py" else "assert True\n")
    package = build(tmp_path, data, **files)
    started = time.monotonic()
    assert sim_audit.main([str(package), flag, "--timeout", "1", "--json"]) == 1
    assert time.monotonic() - started < 6
    results = json.loads(capsys.readouterr().out)["results"]
    failed = [r["detail"] for r in results if r["check"] == check and r["status"] == FAIL]
    assert len(failed) == 1 and ("timed out after 1 s" in failed[0] or "exited 124" in failed[0])


def test_a_package_reached_through_a_symlink_is_audited(tmp_path):
    silent = "print('nothing checked')\n"
    package = build(tmp_path / "real", **{"test/print.test.py": silent})
    link = tmp_path / "link"
    link.symlink_to(package, target_is_directory=True)
    audit = static(link)
    assert "test/print.test.py: contains no assertion" in failures(audit, "asserting")


# Flags not given report SKIP, never PASS


def test_without_flags_nothing_is_run_and_nothing_is_passed_off_as_run(tmp_path):
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": f"{PY} tools/gate.py"}]
    audit = static(build(tmp_path, data, **{"tools/gate.py": "assert False\n"}))
    assert statuses(audit, "suite") == [SKIP]
    assert statuses(audit, "mutations") == [SKIP]
    assert statuses(audit, "gates") == [SKIP]
    assert statuses(audit, "quoted") == [PASS, SKIP]


def test_a_wrong_number_passes_without_the_report_and_fails_with_it(tmp_path):
    data = ledger()
    claim(data, "fall-time")["quoted"] = ["1.234 s"]
    readme = read("README.md").replace("1.010 s", "1.234 s")
    package = build(tmp_path, data, **{"README.md": readme})
    assert not static(package).failed(strict=False)
    audit = sim_audit.audit_package(package, run_report=True)
    assert audit.failed(strict=False)
    assert "fall-time: '1.234 s' is not in the report output" in failures(audit, "quoted")


# Commands run in a copy


def test_commands_write_only_to_the_copy_and_never_see_the_package_changed(tmp_path):
    marker = tmp_path / "live-changed"
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": f"{PY} tools/gate.py"}]
    package = build(tmp_path, data)
    live_model = package / "src" / "model.py"
    spy = (
        "import os\n"
        f"if 'G = 9.80665' not in open({str(live_model)!r}).read():\n"
        f"    open({str(marker)!r}, 'w').write('changed')\n"
        "open('written-by-' + os.path.basename(__file__), 'w').write('x')\n"
    )
    for name in (TABLE, "tools/report.py"):
        (package / name).write_text(spy + read(name), encoding="utf-8")
    (package / "tools" / "gate.py").write_text(spy + "assert True\n", encoding="utf-8")
    before = snapshot(package)
    audit = sim_audit.audit_package(package, run_report=True, run_mutations=True, run_gates=True)
    assert "weaker-gravity: killed" in passes(audit, "mutations")
    assert statuses(audit, "gates") == [PASS]
    assert not audit.failed(strict=False), sim_audit.render(audit, False)
    assert not marker.exists()
    assert snapshot(package) == before


def test_bytecode_caching_is_off_for_every_command(tmp_path):
    data = ledger()
    data["commands"]["test"] = f'{PY} -c "import sys; sys.exit(0 if sys.dont_write_bytecode else 7)"'
    audit = sim_audit.audit_package(build(tmp_path, data), run_tests=True)
    assert statuses(audit, "suite") == [PASS]


def test_consecutive_same_length_mutations_each_run_their_own_code(tmp_path):
    data = ledger()
    mutation(data, "weaker-gravity")["replace"] = "G = 9.70665"
    harmless = {
        "id": "harmless",
        "claim": "fall-time",
        "file": "src/model.py",
        "find": '"""Seconds to fall `height` metres from rest."""',
        "replace": '"""seconds to fall `height` metres from rest."""',
        "command": mutation(data, "weaker-gravity")["command"],
    }
    data["mutations"] = [mutation(data, "weaker-gravity"), harmless]
    text = details(sim_audit.audit_package(build(tmp_path, data), run_mutations=True), "mutations")
    assert "weaker-gravity: killed" in text
    assert "harmless: SURVIVED" in text


def test_the_copy_links_top_level_directories_and_leaves_caches_behind(tmp_path):
    package = build(
        tmp_path,
        **{
            "node_modules/big/file.txt": "x",
            "src/node_modules/kept.txt": "x",
            ".git/HEAD": "ref",
            "src/__pycache__/model.cpython-312.pyc": "stale",
            ".pytest_cache/v": "x",
        },
    )
    (package / "cache").mkdir()
    target = tmp_path / "copy"
    sim_audit.copy_package(package.resolve(), target, ("node_modules", "cache", "absent"))
    assert (target / "node_modules").is_symlink()
    assert (target / "cache").is_symlink()
    assert not os.path.lexists(target / "absent")
    assert not (target / ".git").exists()
    assert not (target / "src" / "__pycache__").exists()
    assert not (target / ".pytest_cache").exists()
    assert (target / "src" / "node_modules" / "kept.txt").is_file()
    assert not (target / "src" / "node_modules").is_symlink()
    assert (target / "src" / "model.py").is_file() and not (target / "src").is_symlink()


def test_the_ledgers_link_list_is_used(tmp_path):
    data = ledger()
    data["link"] = ["vendor"]
    probe = (
        read(TABLE)
        + "\nimport os\nassert os.path.islink('vendor'), 'vendor was copied'\n"
        + "assert not os.path.islink('node_modules'), 'node_modules was linked'\n"
    )
    package = build(
        tmp_path, data, **{TABLE: probe, "vendor/x.txt": "x", "node_modules/y.txt": "y"}
    )
    assert statuses(sim_audit.audit_package(package, run_tests=True), "suite") == [PASS]


def test_a_package_that_cannot_be_copied_is_refused_with_exit_2(tmp_path, capsys):
    package = build(tmp_path)
    os.mkfifo(package / "src" / "pipe")
    assert not static(package).failed(strict=False)  # nothing is copied unless something runs
    assert sim_audit.main([str(package), "--run-tests"]) == 2
    err = capsys.readouterr().err
    assert "cannot copy the package" in err and "Traceback" not in err


# suite


def test_a_red_suite_fails_even_with_no_mutation_naming_it(tmp_path):
    broken = read(TABLE) + "assert False\n"
    data = ledger()
    for entry in data["mutations"]:
        entry["command"] = f"{PY} -c pass"
    audit = sim_audit.audit_package(build(tmp_path, data, **{TABLE: broken}), run_tests=True)
    assert statuses(audit, "suite") == [FAIL]
    assert "exit 1 in a copy of the package" in failures(audit, "suite")


def test_run_mutations_implies_running_the_suite(tmp_path):
    audit = sim_audit.audit_package(build(tmp_path), run_mutations=True)
    assert statuses(audit, "suite") == [PASS]


def test_running_the_suite_needs_a_test_command(tmp_path):
    data = ledger()
    del data["commands"]["test"]
    audit = sim_audit.audit_package(build(tmp_path, data), run_tests=True)
    assert "no `commands.test`" in failures(audit, "suite")


def test_output_that_is_not_text_does_not_crash_the_audit(tmp_path):
    report = "import sys\nsys.stdout.buffer.write(b'\\xff\\xfe 1.010 s 9.90 m/s\\n')\n"
    audit = sim_audit.audit_package(build(tmp_path, **{"tools/report.py": report}), run_report=True)
    assert "2 quoted values are printed by the report" in passes(audit, "quoted")


# gates


def test_a_gate_is_run_only_when_asked_and_a_red_gate_fails(tmp_path):
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": f"{PY} tools/gate.py"}]
    claim(data, "energy")["test"] = "tools/gate.py"
    red = build(tmp_path / "red", data, **{"tools/gate.py": "assert False, 'render gate is red'\n"})
    audit = sim_audit.audit_package(red, run_report=True, run_mutations=True)
    assert statuses(audit, "gates") == [SKIP]
    assert not audit.failed(strict=False) and audit.failed(strict=True)
    audit = sim_audit.audit_package(red, run_gates=True)
    assert "tools/gate.py: exit 1" in failures(audit, "gates")

    green = build(tmp_path / "green", data, **{"tools/gate.py": "assert True\n"})
    audit = sim_audit.audit_package(green, run_report=True, run_mutations=True, run_gates=True)
    assert statuses(audit, "gates") == [PASS]
    assert not audit.failed(strict=True), sim_audit.render(audit, True)
    assert sim_audit.main([str(green), "--run-gates"]) == 0
    assert sim_audit.main([str(red), "--run-gates"]) == 1


def test_a_gate_must_exist_and_must_assert(tmp_path):
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/absent.py", "command": "true"}]
    audit = static(build(tmp_path / "absent", data))
    assert "tools/absent.py: gate file does not exist" in failures(audit, "ledger")
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/report.py", "command": "true"}]
    claim(data, "energy")["test"] = "tools/report.py"
    audit = static(build(tmp_path / "silent", data))
    assert "energy: tools/report.py contains no assertion" in failures(audit, "claims")


# asserting


def test_a_test_file_that_only_prints_fails(tmp_path):
    printing = "import sys\nsys.path.insert(0, 'src')\nfrom model import fall_time\nprint(fall_time(5.0))\n"
    audit = static(build(tmp_path, **{"test/print.test.py": printing}))
    assert "test/print.test.py: contains no assertion" in failures(audit, "asserting")
    assert PASS not in statuses(audit, "asserting")


NOT_ASSERTIONS = [
    ("a.py", "x = 1\n# assert x == 2\nprint(x)\n"),
    ("b.py", "x = 1\nprint(x)  # assert x == 2\n"),
    ("c.ts", "const x = 1\n// expect(x).toBe(2)\nconsole.log(x)\n"),
    ("d.ts", "const x = 1\nconsole.log(x) // expect(x).toBe(2)\n"),
    ("e.ts", "/*\n * expect(x).toBe(2)\n */\nconsole.log(1)\n"),
    ("f.ts", "console.assert(x === 2)\n"),
    ("g.py", "print(f'{x:.3f}')\n"),
    ("h.ts", "process.exit(0)\n"),
    ("i.jl", '@testset "empty" begin\nend\n'),
    ("j.ts", "console.log(x) /* expect(x).toBe(2) */\n"),
    ("k.lua", "print(x) -- assert(x == 2)\n"),
    ("l.py", "def assert_close(a, b):\n    print(a, b)\n"),
    ("m.ts", "function expect(x) {\n  return x\n}\n"),
    ("n.py", "print('this should work')\n"),
    ("o.js", "const path = require.resolve('./x')\n"),
    ("p.py", "print(expected(x))\n"),
    ("q.unknown", "# assert x\n// expect(x)\n"),
    ("r.ts", "process.exitCode = 0\n"),
]
# One file per comment family: the marker must be stripped for every suffix.
NOT_ASSERTIONS += [(f"slash{s}", "x()\n// assert(x)\ny() // assert(y)\n") for s in sorted(sim_audit.SLASH_COMMENTS)]
NOT_ASSERTIONS += [(f"hash{s}", "x()\n# assert x\ny() # assert y\n") for s in sorted(sim_audit.HASH_COMMENTS)]
NOT_ASSERTIONS += [(f"dash{s}", "x()\n-- assert(x)\n") for s in sorted(sim_audit.DASH_COMMENTS)]


def test_the_comment_tables_have_not_shrunk():
    assert len(sim_audit.SLASH_COMMENTS) == 19
    assert len(sim_audit.HASH_COMMENTS) == 10
    assert sim_audit.DASH_COMMENTS == {".lua", ".hs", ".sql", ".elm"}
    assert {".ts", ".rs", ".go", ".cpp", ".java"} <= sim_audit.SLASH_COMMENTS
    assert {".py", ".rb", ".jl", ".sh"} <= sim_audit.HASH_COMMENTS


@pytest.mark.parametrize(("name", "text"), NOT_ASSERTIONS)
def test_text_that_cannot_fail_is_not_an_assertion(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    assert not sim_audit.has_assertion(path)


@pytest.mark.parametrize(
    ("name", "line"),
    [
        ("a.ts", "expect(range).toBeCloseTo(4.16, 2)"),
        ("b.py", "assert abs(x - 1) < 0.01"),
        ("c.py", "self.assertAlmostEqual(x, 1.0)"),
        ("d.rs", "assert_eq!(a, b);"),
        ("e.cc", "EXPECT_NEAR(a, b, 1e-6);"),
        ("f.cc", "ASSERT_TRUE(ok);"),
        ("g.cc", "REQUIRE(range == Approx(4.16));"),
        ("g2.cc", "CHECK(range > 0);"),
        ("g3.cc", "BOOST_CHECK_CLOSE(a, b, 0.1);"),
        ("h.go", 't.Fatalf("got %v", x)'),
        ("h2.go", "require.InDelta(t, 4.16, x, 0.01)"),
        ("h3.go", "os.Exit(1)"),
        ("i.ts", "if (bad) process.exit(1)"),
        ("j.ts", "if (bad) process.exitCode = 1"),
        ("k.ts", "if (bad) throw new Error('range')"),
        ("k2.ts", "/* c8 ignore next */ if (bad) throw new Error('range')"),
        ("l.py", "raise AssertionError('range')"),
        ("l2.py", "sys.exit(2)"),
        ("m.py", "with pytest.raises(ValueError):"),
        ("m2.py", "pytest.fail('range')"),
        ("n.jl", "@test range ≈ 4.16"),
        ("o.cs", "Assert.That(range, Is.EqualTo(4.16));"),
        ("p.mjs", "strictEqual(range, 4.16)"),
        ("p2.mjs", "deepStrictEqual(a, b)"),
        ("p3.mjs", "deepEqual(a, b)"),
        ("p4.mjs", "notStrictEqual(a, b)"),
        ("p5.mjs", "notEqual(a, b)"),
        ("q.mjs", "assert.equal(range, 4.16)"),
        ("r.rb", "range.should eq(4.16)"),
        ("r2.rb", "assert_in_delta 4.16, range, 0.01"),
        ("r3.kt", "range shouldBe 4.16"),
        ("r4.scala", "range should be (4.16)"),
        ("s.ts", "const r = await fetch('https://x.org/a'); expect(r.ok).toBe(true)"),
        ("t.py", "paths = glob('ref/*.txt')\nassert paths\nother = glob('**/x')"),
        ("u.py", "x = 10 // 2; assert x == 5"),
        ("u2.py", "x = glob('a/*'); assert x; y = glob('*/b')"),
        ("u3.ts", "const s = ' #'; expect(s).toBe(' #')"),
        ("u4.ts", "let i = 3; i--; expect(i).toBe(2)"),
        ("u5.js", "x.should.equal(4)"),
        ("v.swift", "XCTAssertEqual(range, 4.16, accuracy: 0.01)"),
        ("w.r", "expect_equal(range, 4.16)"),
        ("x.zig", "try expectApproxEqAbs(4.16, range, 0.01);"),
        ("y.nim", "doAssert range > 0"),
        ("z.rs", 'panic!("range");'),
        ("z2.go", 'panic("range")'),
        ("z3.sh", "exit(3)"),
    ],
)
def test_assertion_constructs_are_recognised(tmp_path, name, line):
    path = tmp_path / name
    path.write_text(f"setup()\n{line}\n", encoding="utf-8")
    assert sim_audit.has_assertion(path)


def test_a_ledger_can_name_its_own_assertion_construct(tmp_path):
    custom = "from model import fall_time\nverify(fall_time(0.0) == 0.0)\n"
    custom += 'open("test/reference/drop.txt")\n'
    data = ledger()
    audit = static(build(tmp_path / "builtin", data, **{TABLE: custom}))
    assert "test/table.test.py: contains no assertion" in failures(audit, "asserting")
    data["tests"]["assertion"] = r"\bverify\(|\bassert\b"
    audit = static(build(tmp_path / "custom", data, **{TABLE: custom}))
    assert statuses(audit, "asserting") == [PASS]
    data["tests"]["assertion"] = r"\bverify\("
    audit = static(build(tmp_path / "only", data, **{TABLE: custom}))
    assert "test/energy.test.py: contains no assertion" in failures(audit, "asserting")


@pytest.mark.parametrize("directory", ["nowhere", "..", "README.md"])
def test_no_test_files_at_all_fails(tmp_path, directory):
    data = ledger()
    data["tests"]["dir"] = directory
    audit = static(build(tmp_path, data))
    assert statuses(audit, "asserting") == [FAIL]
    assert "is neither a test file nor listed" in failures(audit, "claims")


# claims


def test_a_checked_claim_needs_an_existing_test(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "test/absent.test.py"
    del claim(data, "zero-height")["test"]
    text = failures(static(build(tmp_path, data)), "claims")
    assert "energy: test file test/absent.test.py does not exist" in text
    assert "zero-height: a control claim needs a `test` file" in text


def test_a_claims_test_must_be_a_test_file_or_a_declared_gate(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "src/model.py"
    model = read("src/model.py") + "\n\ndef check(x):\n    raise ValueError(x)\n"
    package = build(tmp_path / "undeclared", data, **{"src/model.py": model})
    assert "energy: src/model.py is neither a test file nor listed" in failures(
        static(package), "claims"
    )

    gate = "import sys\nif len(sys.argv) > 9:\n    raise SystemExit('render gate failed')\n"
    data = ledger()
    claim(data, "energy")["test"] = "tools/gate.py"
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": "true"}]
    audit = static(build(tmp_path / "declared", data, **{"tools/gate.py": gate}))
    assert "energy: conservation: tools/gate.py, and a mutation names it" in passes(audit, "claims")


def test_a_checked_claim_without_a_mutation_warns(tmp_path):
    data = ledger()
    data["mutations"] = [m for m in data["mutations"] if m["claim"] == "fall-time"]
    audit = full(build(tmp_path, data))
    warned = [r.subject for r in audit.results if r.check == "claims" and r.status == WARN]
    assert warned == ["fall-time-stepped", "energy", "zero-height"]
    assert "fall-time: reference: test/table.test.py, and a mutation names it" in passes(
        audit, "claims"
    )
    assert not audit.failed(strict=False)
    assert audit.failed(strict=True)


def test_a_test_path_outside_the_package_is_refused(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "../outside.test.py"
    (tmp_path / "outside.test.py").write_text("assert True\n", encoding="utf-8")
    audit = static(build(tmp_path, data))
    assert "energy: test file ../outside.test.py does not exist" in failures(audit, "claims")


# references


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("# Fetched 2026-11-13\n", "no source URL"),
        ("# Source: https://example.org/t\n", "no fetch date"),
        ("# Source: ftp://example.org/t, 2026-11-13\n", "no source URL"),
        ("# Source: https://example.org/t, 2026-13-10\n", "no fetch date"),
        ("# Source: https://example.org/t, 2026-11-40\n", "no fetch date"),
        ("# Source: https://example.org/t, 12026-11-13\n", "no fetch date"),
        ("#\n" * 40 + "# https://example.org/t 2026-11-13\n", "no source URL; no fetch date"),
    ],
)
def test_a_reference_without_provenance_in_its_header_fails(tmp_path, header, problem):
    table = header + "5.0 1.0098\n20.0 2.0196\n"
    audit = static(build(tmp_path, **{"test/reference/drop.txt": table}))
    assert f"drop-table: {problem}" in failures(audit, "references")


@pytest.mark.parametrize(
    "header",
    [
        "# http://example.org/t fetched 2026-11-13\n",
        "#\n" * 39 + "# https://example.org/t 1999-01-31\n",
    ],
)
def test_provenance_anywhere_in_the_first_forty_lines_is_accepted(tmp_path, header):
    table = header + "1.0 0.4516\n5.0 1.0098\n20.0 2.0196\n100.0 4.5160\n"
    audit = static(build(tmp_path, **{"test/reference/drop.txt": table}))
    assert "drop-table: test/reference/drop.txt: sourced, dated and read" in passes(
        audit, "references"
    )


def test_a_reference_no_test_reads_fails(tmp_path):
    source = read(TABLE)
    opened = 'open("test/reference/drop.txt", encoding="utf-8")'
    assert opened in source
    retyped = source.replace(opened, 'open("README.md", encoding="utf-8")')
    audit = static(build(tmp_path / "plain", **{TABLE: retyped}))
    assert "drop-table: no test reads it" in failures(audit, "references")

    commented = retyped + "# numbers typed from drop.txt\n"
    audit = static(build(tmp_path / "comment", **{TABLE: commented}))
    assert "drop-table: no test reads it" in failures(audit, "references")

    assert sim_audit.DATA_SUFFIXES == {".txt", ".csv", ".tsv", ".dat", ".json", ".md"}
    for suffix in (".txt", ".csv", ".tsv", ".dat", ".json", ".md"):
        note = {f"test/reference/notes{suffix}": "see drop.txt\n"}
        audit = static(build(tmp_path / f"data{suffix}", **{TABLE: retyped, **note}))
        assert "drop-table: no test reads it" in failures(audit, "references"), suffix


def test_a_helper_beside_the_tests_may_read_the_reference(tmp_path):
    source = read(TABLE)
    helped = source.replace('open("test/reference/drop.txt", encoding="utf-8")', "load_table()")
    helped = helped.replace("from model import", "from loader import load_table\nfrom model import")
    helped = helped.replace('sys.path.insert(0, "src")', 'sys.path[:0] = ["src", "test"]')
    assert helped.count("load_table") == 2 and '["src", "test"]' in helped
    loader = 'def load_table():\n    return open("test/reference/drop.txt", encoding="utf-8")\n'
    audit = full(build(tmp_path, **{TABLE: helped, "test/loader.py": loader}))
    assert "drop-table: test/reference/drop.txt: sourced, dated and read" in passes(
        audit, "references"
    )
    assert not audit.failed(strict=True), sim_audit.render(audit, True)


def test_a_gate_may_read_the_reference(tmp_path):
    source = read(TABLE)
    retyped = source.replace(
        'open("test/reference/drop.txt", encoding="utf-8")', 'open("README.md", encoding="utf-8")'
    )
    data = ledger()
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": "true"}]
    gate = 'rows = open("test/reference/drop.txt").read()\nassert rows\n'
    audit = static(build(tmp_path, data, **{TABLE: retyped, "tools/gate.py": gate}))
    assert "drop-table: test/reference/drop.txt: sourced, dated and read" in passes(
        audit, "references"
    )


def test_reference_bookkeeping_errors_fail(tmp_path):
    data = ledger()
    data["references"].append({"id": "spare", "path": "test/reference/drop.txt"})
    data["references"].append({"id": "gone", "path": "test/reference/gone.txt"})
    data["references"].append({"id": "outside", "path": "../drop.txt"})
    (tmp_path / "drop.txt").write_text(read("test/reference/drop.txt"), encoding="utf-8")
    claim(data, "fall-time")["reference"] = "typo"
    text = failures(static(build(tmp_path, data)), "references")
    assert "fall-time: names unknown reference 'typo'" in text
    assert "spare: no claim uses it" in text
    assert "gone: test/reference/gone.txt does not exist in the package" in text
    assert "outside: ../drop.txt does not exist in the package" in text

    data = ledger()
    claim(data, "fall-time")["reference"] = ["drop-table"]
    assert "fall-time: names unknown reference" in failures(
        static(build(tmp_path / "list", data)), "references"
    )


def test_a_reference_claim_may_cite_a_source_instead_of_a_stored_table(tmp_path):
    data = ledger()
    data["claims"].append(
        {
            "id": "g",
            "kind": "reference",
            "statement": "g is the standard value.",
            "test": TABLE,
            "source": "CODATA, standard acceleration of gravity",
        }
    )
    audit = static(build(tmp_path / "cited", data))
    assert "g: cited: CODATA, standard acceleration of gravity" in passes(audit, "references")
    for bad in (" ", 5):
        data["claims"][-1]["source"] = bad
        audit = static(build(tmp_path / f"blank{bad}", data))
        assert "g: a reference claim needs `reference`" in failures(audit, "references")


# coverage


@pytest.mark.parametrize(
    ("drop", "message"),
    [
        ({"zero-height"}, "no negative control"),
        ({"fall-time", "fall-time-stepped"}, "no anchor outside the model"),
        ({"g-value", "no-drag"}, "no stated limit"),
    ],
)
def test_each_missing_kind_of_claim_fails_coverage(tmp_path, drop, message):
    data = ledger()
    data["claims"] = [c for c in data["claims"] if c["id"] not in drop]
    data["mutations"] = [m for m in data["mutations"] if m["claim"] not in drop]
    data["references"] = [] if "fall-time" in drop else data["references"]
    audit = static(build(tmp_path, data))
    assert statuses(audit, "coverage") == [FAIL]
    assert message in failures(audit, "coverage")


@pytest.mark.parametrize("drop", ["fall-time", "fall-time-stepped", "g-value", "no-drag"])
def test_one_claim_of_each_pair_is_enough_for_coverage(tmp_path, drop):
    data = ledger()
    data["claims"] = [c for c in data["claims"] if c["id"] != drop]
    data["mutations"] = [m for m in data["mutations"] if m["claim"] != drop]
    data["references"] = [] if drop == "fall-time" else data["references"]
    audit = static(build(tmp_path, data))
    assert statuses(audit, "coverage") == [PASS]
    assert f"control 1, prediction 1" in passes(audit, "coverage")


def test_neither_a_conservation_claim_nor_a_prediction_stands_in(tmp_path):
    data = ledger()
    for entry in data["claims"]:
        if entry["kind"] in {"reference", "independent"}:
            entry["kind"] = "conservation"
            entry.pop("reference", None)
        if entry["kind"] in {"convention", "omitted"}:
            entry["kind"] = "prediction"
    data["references"] = []
    text = failures(static(build(tmp_path, data)), "coverage")
    assert "no anchor outside the model" in text and "no stated limit" in text
    assert "no negative control" not in text

    data = ledger()
    claim(data, "zero-height")["kind"] = "reference"
    claim(data, "zero-height")["source"] = "x"
    assert "no negative control" in failures(static(build(tmp_path / "c", data)), "coverage")


# quoted


def test_a_quoted_value_missing_from_the_docs_fails(tmp_path):
    audit = static(build(tmp_path, **{"README.md": "A body falls. It lands at 9.90 m/s.\n"}))
    assert "fall-time: '1.010 s' is in the ledger but not in the docs" in failures(audit, "quoted")
    assert passes(audit, "quoted") == ""


def test_every_listed_doc_is_searched(tmp_path):
    data = ledger()
    data["docs"] = ["README.md", "docs/more.md"]
    audit = static(build(tmp_path / "second", data, **{"docs/more.md": "Nothing here.\n"}))
    assert "2 quoted values appear in the docs" in passes(audit, "quoted")
    audit = static(
        build(
            tmp_path / "first",
            data,
            **{"README.md": "Nothing here.\n", "docs/more.md": read("README.md")},
        )
    )
    assert "2 quoted values appear in the docs" in passes(audit, "quoted")


def test_a_missing_doc_fails(tmp_path):
    data = ledger()
    data["docs"] = ["README.md", "docs/absent.md"]
    assert "doc docs/absent.md does not exist" in failures(static(build(tmp_path, data)), "quoted")


def test_report_command_failures_fail(tmp_path):
    crashing = build(tmp_path / "crash", **{"tools/report.py": "raise SystemExit(3)\n"})
    audit = sim_audit.audit_package(crashing, run_report=True)
    assert "report command exited 3" in failures(audit, "quoted")

    data = ledger()
    del data["commands"]["report"]
    audit = sim_audit.audit_package(build(tmp_path / "none", data), run_report=True)
    assert "no `commands.report`" in failures(audit, "quoted")


def test_quoted_values_match_exactly_including_case(tmp_path):
    data = ledger()
    claim(data, "energy")["quoted"] = ["9.90 M/S"]
    readme = read("README.md").replace("9.90 m/s", "9.90 M/S")
    audit = sim_audit.audit_package(build(tmp_path, data, **{"README.md": readme}), run_report=True)
    assert "energy: '9.90 M/S' is not in the report output" in failures(audit, "quoted")
    audit = static(build(tmp_path / "docs", data))
    assert "energy: '9.90 M/S' is in the ledger but not in the docs" in failures(audit, "quoted")


def test_a_number_printed_only_to_standard_error_does_not_count(tmp_path):
    original = read("tools/report.py")
    report = original.replace(
        'print(f"fall time from 5 m:     {fall_time(5.0):.3f} s")',
        'print(f"fall time from 5 m:     {fall_time(5.0):.3f} s", file=sys.stderr)',
    )
    assert report != original
    audit = sim_audit.audit_package(build(tmp_path, **{"tools/report.py": report}), run_report=True)
    assert "fall-time: '1.010 s' is not in the report output" in failures(audit, "quoted")
    assert "printed by the report" not in passes(audit, "quoted")


@pytest.mark.parametrize("quoted", [[9.999], ["1.010 s", 9.999], [""], ["  "], "1.010 s"])
def test_quoted_values_must_be_non_empty_strings(tmp_path, quoted):
    data = ledger()
    claim(data, "fall-time")["quoted"] = quoted
    audit = static(build(tmp_path, data))
    assert "fall-time: `quoted` must be a list of non-empty strings" in failures(audit, "ledger")
    assert audit.failed(strict=False)


def test_no_quoted_values_warns(tmp_path):
    data = ledger()
    for entry in data["claims"]:
        entry.pop("quoted", None)
    assert statuses(static(build(tmp_path, data)), "quoted") == [WARN]


# mutations


def test_a_surviving_mutation_fails(tmp_path):
    weak = read("test/energy.test.py").replace("< 1e-9 * G * height", "< 1.0 * G * height")
    assert weak != read("test/energy.test.py")
    audit = full(build(tmp_path, **{"test/energy.test.py": weak}))
    assert audit.failed(strict=False)
    assert "faster-impact: SURVIVED" in failures(audit, "mutations")
    assert "weaker-gravity: killed" in passes(audit, "mutations")


def test_each_mutation_starts_from_the_original_file(tmp_path):
    data = ledger()
    data["mutations"].append(
        {
            "id": "harmless",
            "claim": "energy",
            "file": "src/model.py",
            "find": '"""Speed on reaching the ground, m/s."""',
            "replace": '"""Speed at the ground, m/s."""',
        }
    )
    audit = full(build(tmp_path, data))
    assert "never-instant: killed" in passes(audit, "mutations")
    assert "harmless: SURVIVED" in failures(audit, "mutations")


def test_a_mutations_own_command_is_used_and_the_default_is_the_suite(tmp_path):
    data = ledger()
    mutation(data, "weaker-gravity")["command"] = f"{PY} -c pass"
    del mutation(data, "never-instant")["command"]
    audit = full(build(tmp_path, data))
    assert "weaker-gravity: SURVIVED" in failures(audit, "mutations")
    assert "never-instant: killed" in passes(audit, "mutations")


MODEL = "src/model.py"


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        ({"find": "G = 1.62"}, "`find` occurs 0 times in src/model.py"),
        ({"find": "height"}, "`find` occurs 5 times in src/model.py; it must occur once"),
        ({"file": "src/absent.py"}, "src/absent.py does not exist in the package"),
        ({"file": "../model.py"}, "../model.py does not exist in the package"),
        ({"file": TABLE, "find": "assert len(rows) >= 2"}, "is a test, a gate, or a file beside"),
        ({"file": "test/reference/drop.txt", "find": "5.0 1.0098"}, "is a test, a gate, or"),
        ({"file": "test/tol.py", "find": "TOL = 1e-3"}, "is a test, a gate, or a file beside"),
        ({"file": "tools/gate.py", "find": "assert True"}, "is a test, a gate, or a file beside"),
        ({"file": "lib/model.py"}, "is in a linked directory"),
        ({"file": "lib/deep/model.py"}, "is in a linked directory"),
        ({"file": "src/latin1.py", "find": "x"}, "src/latin1.py is not UTF-8"),
    ],
)
def test_a_mutation_that_cannot_be_trusted_fails_without_running(tmp_path, edit, message):
    data = ledger()
    data["link"] = ["lib"]
    data["tests"]["gates"] = [{"file": "tools/gate.py", "command": "true"}]
    mutation(data, "weaker-gravity").update(edit)
    (tmp_path / "model.py").write_text(read(MODEL), encoding="utf-8")
    package = build(
        tmp_path,
        data,
        **{
            "lib/model.py": read(MODEL),
            "lib/deep/model.py": read(MODEL),
            "test/tol.py": "TOL = 1e-3\n",
            "tools/gate.py": "assert True\n",
        },
    )
    (package / "src" / "latin1.py").write_bytes("x = 'café'\n".encode("latin-1"))
    audit = static(package)
    failed = [r.detail for r in audit.results if r.subject == "weaker-gravity" and r.status == FAIL]
    assert len(failed) == 1 and message in failed[0]
    assert "3 mutations apply" in details(audit, "mutations", SKIP)


def test_a_test_file_spelled_in_another_case_is_still_a_test(tmp_path):
    data = ledger()
    data["link"] = ["lib"]
    package = build(tmp_path, data, **{"lib/model.py": read(MODEL)})
    if not (package / "TEST").exists():
        pytest.skip("the file system is case-sensitive")
    mutation(data, "weaker-gravity").update(file="Test/table.test.py", find="assert len(rows) >= 2")
    mutation(data, "never-instant").update(file="LIB/model.py")
    (package / "sim-claims.json").write_text(json.dumps(data), encoding="utf-8")
    text = failures(static(package), "mutations")
    assert "weaker-gravity: Test/table.test.py is a test" in text
    assert "never-instant: LIB/model.py is in a linked directory" in text


def test_a_mutation_with_no_command_at_all_fails(tmp_path):
    data = ledger()
    del data["commands"]["test"]
    del mutation(data, "weaker-gravity")["command"]
    audit = static(build(tmp_path, data))
    assert "weaker-gravity: no `command` and no `commands.test`" in failures(audit, "mutations")
    assert "faster-impact" not in failures(audit, "mutations")


def test_tests_that_are_red_before_any_change_fail_every_mutation(tmp_path):
    files = {name: read(name) + "assert False\n" for name in (TABLE, "test/energy.test.py")}
    audit = full(build(tmp_path, **files))
    text = failures(audit, "mutations")
    assert "weaker-gravity: the test command exits 1 before any change" in text
    assert "faster-impact: the test command exits 1 before any change" in text
    assert "never-instant: killed" in passes(audit, "mutations")


def test_a_mutation_that_hangs_is_a_failure_and_leaves_nothing_running(tmp_path):
    pidfile = tmp_path / "pid"
    data = ledger()
    data["mutations"] = [mutation(data, "weaker-gravity")]
    data["mutations"][0]["replace"] = (
        f"import os, time\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\nG = 9.7"
    )
    data["mutations"][0]["command"] = f"{PY} {TABLE}; echo done"
    started = time.monotonic()
    audit = sim_audit.audit_package(build(tmp_path, data), run_mutations=True, timeout=5)
    assert time.monotonic() - started < 30
    assert "weaker-gravity: timed out after 5 s" in failures(audit, "mutations")
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_mutations_that_do_not_apply_are_not_reported_as_waiting_to_run(tmp_path):
    data = ledger()
    for entry in data["mutations"]:
        entry["find"] = "not in the file"
    audit = static(build(tmp_path, data))
    assert statuses(audit, "mutations") == [FAIL] * 4


def test_the_baseline_runs_once_per_command(tmp_path):
    log = tmp_path / "runs"
    command = f"echo run >> {log}; {PY} {TABLE}"
    data = ledger()
    data["mutations"] = [mutation(data, "weaker-gravity"), mutation(data, "never-instant")]
    for entry in data["mutations"]:
        entry["command"] = command
    audit = sim_audit.audit_package(build(tmp_path, data), run_mutations=True)
    assert "weaker-gravity: killed" in passes(audit, "mutations")
    assert log.read_text().count("run") == 3


def test_no_mutations_fails(tmp_path):
    data = ledger()
    data["mutations"] = []
    audit = static(build(tmp_path, data))
    assert statuses(audit, "mutations") == [FAIL]
    assert "no mutations" in failures(audit, "mutations")


# the ledger


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["claims"].append(dict(d["claims"][-1])), "duplicate claim id"),
        (lambda d: d["claims"][-1].update(kind="vibes"), "kind must be one of"),
        (lambda d: d["claims"][-1].update(kind=["omitted"]), "kind must be one of"),
        (lambda d: d["claims"][-1].update(statement=" "), "a claim needs a `statement`"),
        (lambda d: d["claims"][-1].update(statement=5), "a claim needs a `statement`"),
        (lambda d: d["claims"].append({"kind": "omitted"}), "a claim needs a string `id`"),
        (lambda d: d["claims"].append("x"), "a claim needs a string `id`"),
        (lambda d: d["mutations"][0].update(claim="nope"), "unknown claim"),
        (lambda d: d["mutations"][0].update(replace="G = 9.80665"), "identical"),
        (lambda d: d["mutations"][0].pop("find"), "mutation is missing find"),
        (lambda d: d["mutations"][0].pop("replace"), "mutation is missing replace"),
        (lambda d: d["mutations"][0].pop("file"), "mutation is missing file"),
        (lambda d: d["mutations"][0].pop("claim"), "mutation is missing claim"),
        (lambda d: d["mutations"][0].update(command=5), "`command` must be a string"),
        (lambda d: d["mutations"].append(dict(d["mutations"][0])), "duplicate mutation id"),
        (lambda d: d["mutations"].append({"claim": "energy"}), "a mutation needs a string `id`"),
        (lambda d: d["mutations"].append("x"), "a mutation needs a string `id`"),
        (lambda d: d["references"].append(dict(d["references"][0])), "duplicate reference id"),
        (lambda d: d["references"].append({"id": ["x"], "path": "y"}), "a reference needs"),
        (lambda d: d["references"].append({"id": "x", "path": 5}), "a reference needs"),
        (lambda d: d["references"].append("x"), "a reference needs"),
    ],
)
def test_malformed_ledger_entries_fail(tmp_path, edit, message):
    data = ledger()
    edit(data)
    audit = static(build(tmp_path, data))
    assert message in failures(audit, "ledger")
    assert PASS not in statuses(audit, "ledger")
    assert audit.failed(strict=False)


def test_a_mutation_of_a_claim_the_ledger_rejected_is_rejected_too(tmp_path):
    data = ledger()
    claim(data, "energy")["kind"] = "vibes"
    assert "faster-impact: mutation names unknown claim 'energy'" in failures(
        static(build(tmp_path, data)), "ledger"
    )


def test_a_ledger_with_no_claims_fails(tmp_path):
    data = ledger()
    data["claims"], data["mutations"], data["references"] = [], [], []
    assert "the ledger has no valid claims" in failures(static(build(tmp_path, data)), "ledger")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d.update(commands="x"), "`commands` must map"),
        (lambda d: d.update(commands={"test": 5}), "`commands` must map"),
        (lambda d: d.update(commands={"test": " "}), "`commands` must map"),
        (lambda d: d.update(tests=[]), "`tests` must be a mapping"),
        (lambda d: d["tests"].update(dir=5), "`tests.dir` must be a string"),
        (lambda d: d["tests"].update(dir=" "), "`tests.dir` must be a string"),
        (lambda d: d["tests"].update(glob=[5]), "`glob` must be a list"),
        (lambda d: d["tests"].update(glob=5), "`glob` must be a list"),
        (lambda d: d["tests"].update(assertion="("), "not a regular expression"),
        (lambda d: d["tests"].update(assertion=5), "`tests.assertion` must be a string"),
        (lambda d: d["tests"].update(gates="tools/gate.py"), "`tests.gates` must be a list"),
        (lambda d: d["tests"].update(gates=["tools/gate.py"]), "needs a `file` and a `command`"),
        (lambda d: d["tests"].update(gates=[{"file": "x"}]), "needs a `file` and a `command`"),
        (lambda d: d["tests"].update(gates=[{"command": "x"}]), "needs a `file` and a `command`"),
        (lambda d: d["tests"].update(gates=[{"file": " ", "command": "x"}]), "needs a `file`"),
        (lambda d: d["tests"].update(gates=[{"file": "x", "command": " "}]), "needs a `file`"),
        (lambda d: d.update(docs=[5]), "`docs` must be a list"),
        (lambda d: d.update(docs=[" "]), "`docs` must be a list"),
        (lambda d: d.update(link=["../x"]), "top-level directory names"),
        (lambda d: d.update(link=[".."]), "top-level directory names"),
        (lambda d: d.update(link=["."]), "top-level directory names"),
        (lambda d: d.update(link=["sub/node_modules"]), "top-level directory names"),
        (lambda d: d.update(link=["sub\\node_modules"]), "top-level directory names"),
        (lambda d: d.update(claims={"a": 1}), "`claims` must be a list"),
    ],
)
def test_a_ledger_of_the_wrong_shape_is_refused_with_exit_2(tmp_path, capsys, edit, message):
    data = ledger()
    edit(data)
    package = build(tmp_path, data)
    with pytest.raises(sim_audit.LedgerError) as caught:
        static(package)
    assert message in str(caught.value)
    assert sim_audit.main([str(package)]) == 2
    assert "Traceback" not in capsys.readouterr().err


def test_a_bare_string_is_accepted_where_a_list_of_one_is_meant(tmp_path):
    data = ledger()
    data["docs"] = "README.md"
    data["tests"]["glob"] = "*.test.py"
    data["link"] = "node_modules"
    assert not full(build(tmp_path, data)).failed(strict=True)


def test_a_json_ledger_needs_no_yaml_parser(tmp_path, monkeypatch):
    package = build(tmp_path)
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert not static(package).failed(strict=False)
    (package / "sim-claims.json").rename(package / "sim-claims.yaml")
    with pytest.raises(sim_audit.LedgerError, match="PyYAML is not installed"):
        static(package)


def test_unreadable_and_ambiguous_ledgers_are_refused(tmp_path):
    package = build(tmp_path)
    (package / "sim-claims.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError, match="top level must be a mapping"):
        static(package)
    (package / "sim-claims.json").write_bytes(b'{"docs": "caf\xe9"}')
    with pytest.raises(sim_audit.LedgerError, match="is not UTF-8"):
        static(package)
    (package / "sim-claims.json").write_text(json.dumps(ledger()), encoding="utf-8")
    (package / "sim-claims.yaml").write_text("claims: [", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError, match="more than one ledger"):
        static(package)
    (package / "sim-claims.json").unlink()
    with pytest.raises(sim_audit.LedgerError, match="sim-claims.yaml"):
        static(package)
    (package / "sim-claims.yaml").rename(package / "sim-claims.yml")
    with pytest.raises(sim_audit.LedgerError, match="sim-claims.yml"):
        static(package)
