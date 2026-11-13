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


def example_ledger() -> dict:
    data = yaml.safe_load((EXAMPLE / "sim-claims.yaml").read_text(encoding="utf-8"))
    data["commands"] = {k: v.replace("python3 ", f"{PY} ") for k, v in data["commands"].items()}
    for entry in data["mutations"]:
        if "command" in entry:
            entry["command"] = entry["command"].replace("python3 ", f"{PY} ")
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


def full(package: Path, timeout: int = 60) -> sim_audit.Audit:
    return sim_audit.audit_package(package, run_report=True, run_mutations=True, timeout=timeout)


def static(package: Path) -> sim_audit.Audit:
    return sim_audit.audit_package(package)


# The shipped example


def test_the_shipped_example_passes_strictly_from_its_yaml_ledger(tmp_path):
    package = tmp_path / "falling-body"
    shutil.copytree(EXAMPLE, package)
    text = (package / "sim-claims.yaml").read_text(encoding="utf-8")
    (package / "sim-claims.yaml").write_text(text.replace("python3 ", f"{PY} "), encoding="utf-8")
    audit = full(package)
    assert not audit.failed(strict=True), sim_audit.render(audit, True)
    assert {r.status for r in audit.results} == {PASS}
    assert {c["kind"] for c in LEDGER["claims"]} == set(sim_audit.KINDS)


def test_every_check_reports(tmp_path):
    audit = full(build(tmp_path))
    names = {r.check for r in audit.results}
    assert names == {
        "ledger", "asserting", "claims", "references", "coverage", "quoted", "suite", "mutations",
    }  # fmt: skip


# The command line


def test_exit_codes(tmp_path, capsys):
    package = build(tmp_path)
    assert sim_audit.main([str(package), "--run-report", "--run-mutations"]) == 0
    assert sim_audit.main([str(tmp_path / "missing")]) == 2
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
    assert sim_audit.main([str(package), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {r["check"] for r in payload["results"]} >= {"ledger", "asserting", "mutations"}

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


def test_the_timeout_flag_reaches_the_commands(tmp_path, capsys):
    slow = read("test/fall.test.py") + "import time\ntime.sleep(5)\n"
    package = build(tmp_path, **{"test/fall.test.py": slow})
    started = time.monotonic()
    assert sim_audit.main([str(package), "--run-tests", "--timeout", "1"]) == 1
    assert time.monotonic() - started < 4
    assert "timed out after 1 s" in capsys.readouterr().out


def test_a_package_reached_through_a_symlink_is_audited(tmp_path):
    silent = "print('nothing checked')\n"
    package = build(tmp_path / "real", **{"test/print.test.py": silent})
    link = tmp_path / "link"
    link.symlink_to(package, target_is_directory=True)
    audit = static(link)
    assert "test/print.test.py: contains no assertion" in details(audit, "asserting")


# Flags not given report SKIP, never PASS


def test_without_flags_nothing_is_run_and_nothing_is_passed_off_as_run(tmp_path):
    audit = static(build(tmp_path))
    assert statuses(audit, "suite") == [SKIP]
    assert statuses(audit, "mutations") == [SKIP]
    assert statuses(audit, "quoted") == [PASS, SKIP]


def test_a_wrong_number_passes_without_the_report_and_fails_with_it(tmp_path):
    data = ledger()
    claim(data, "fall-time")["quoted"] = ["1.234 s"]
    readme = read("README.md").replace("1.010 s", "1.234 s")
    package = build(tmp_path, data, **{"README.md": readme})
    assert not static(package).failed(strict=False)
    audit = sim_audit.audit_package(package, run_report=True)
    assert audit.failed(strict=False)
    assert "fall-time: '1.234 s' is not in the report output" in details(audit, "quoted")


# suite


def test_a_red_suite_fails_even_with_no_mutation_naming_it(tmp_path):
    broken = read("test/fall.test.py") + "assert False\n"
    data = ledger()
    for entry in data["mutations"]:
        entry["command"] = f"{PY} -c pass"
    audit = sim_audit.audit_package(
        build(tmp_path, data, **{"test/fall.test.py": broken}), run_tests=True
    )
    assert statuses(audit, "suite") == [FAIL]
    assert "exit 1 in a copy of the package" in details(audit, "suite")


def test_run_mutations_implies_running_the_suite(tmp_path):
    audit = sim_audit.audit_package(build(tmp_path), run_mutations=True)
    assert statuses(audit, "suite") == [PASS]


def test_running_the_suite_needs_a_test_command(tmp_path):
    data = ledger()
    del data["commands"]["test"]
    audit = sim_audit.audit_package(build(tmp_path, data), run_tests=True)
    assert "no `commands.test`" in failures(audit, "suite")


# asserting


def test_a_test_file_that_only_prints_fails(tmp_path):
    printing = "import sys\nsys.path.insert(0, 'src')\nfrom model import fall_time\nprint(fall_time(5.0))\n"
    audit = static(build(tmp_path, **{"test/print.test.py": printing}))
    assert FAIL in statuses(audit, "asserting")
    assert "test/print.test.py" in details(audit, "asserting")


@pytest.mark.parametrize(
    ("name", "text"),
    [
        ("a.py", "x = 1\n# assert x == 2\nprint(x)\n"),
        ("b.py", "x = 1\nprint(x)  # assert x == 2\n"),
        ("c.ts", "const x = 1\n// expect(x).toBe(2)\nconsole.log(x)\n"),
        ("d.ts", "const x = 1\nconsole.log(x) // expect(x).toBe(2)\n"),
        ("e.ts", "/*\n * expect(x).toBe(2)\n */\nconsole.log(1)\n"),
        ("f.ts", "console.assert(x === 2)\n"),
        ("g.py", "print(f'{x:.3f}')\n"),
        ("h.ts", "process.exit(0)\n"),
        ("i.jl", '@testset "empty" begin\nend\n'),
    ],
)
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
        ("h.go", 't.Fatalf("got %v", x)'),
        ("i.ts", "if (bad) process.exit(1)"),
        ("j.ts", "if (bad) process.exitCode = 1"),
        ("k.ts", "if (bad) throw new Error('range')"),
        ("l.py", "raise AssertionError('range')"),
        ("m.py", "with pytest.raises(ValueError):"),
        ("n.jl", "@test range ≈ 4.16"),
        ("o.cs", "Assert.That(range, Is.EqualTo(4.16));"),
        ("p.mjs", "strictEqual(range, 4.16)"),
        ("q.mjs", "assert.equal(range, 4.16)"),
        ("r.rb", "range.should eq(4.16)"),
        ("s.ts", "const r = await fetch('https://x.org/a'); expect(r.ok).toBe(true)"),
        ("t.py", "paths = glob('ref/*.txt')\nassert paths\nother = glob('**/x')"),
        ("u.py", "x = 10 // 2; assert x == 5"),
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
    audit = static(build(tmp_path / "builtin", data, **{"test/fall.test.py": custom}))
    assert FAIL in statuses(audit, "asserting")
    data["tests"]["assertion"] = r"\bverify\("
    audit = static(build(tmp_path / "custom", data, **{"test/fall.test.py": custom}))
    assert statuses(audit, "asserting") == [PASS]


def test_no_test_files_at_all_fails(tmp_path):
    data = ledger()
    data["tests"]["dir"] = "nowhere"
    audit = static(build(tmp_path, data))
    assert statuses(audit, "asserting") == [FAIL]


# claims


def test_a_checked_claim_needs_an_existing_test(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "test/absent.test.py"
    del claim(data, "zero-height")["test"]
    text = details(static(build(tmp_path, data)), "claims")
    assert "energy: test file test/absent.test.py does not exist" in text
    assert "zero-height: a control claim needs a `test` file" in text


def test_a_claims_test_must_be_a_test_file_or_a_declared_gate(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "src/model.py"
    model = read("src/model.py") + "\n\ndef check(x):\n    raise ValueError(x)\n"
    package = build(tmp_path / "undeclared", data, **{"src/model.py": model})
    assert "energy: src/model.py is neither a test file nor listed" in details(
        static(package), "claims"
    )

    gate = "import sys\nif len(sys.argv) > 9:\n    raise SystemExit('render gate failed')\n"
    data = ledger()
    claim(data, "energy")["test"] = "tools/gate.py"
    data["tests"]["gates"] = ["tools/gate.py"]
    audit = static(build(tmp_path / "declared", data, **{"tools/gate.py": gate}))
    assert "energy: conservation: tools/gate.py, with a mutation" in details(audit, "claims")


def test_a_gate_must_exist_and_must_assert(tmp_path):
    data = ledger()
    data["tests"]["gates"] = ["tools/absent.py"]
    assert "tools/absent.py: gate file does not exist" in details(
        static(build(tmp_path / "absent", data)), "ledger"
    )
    data = ledger()
    data["tests"]["gates"] = ["tools/report.py"]
    claim(data, "energy")["test"] = "tools/report.py"
    assert "energy: tools/report.py contains no assertion" in details(
        static(build(tmp_path / "silent", data)), "claims"
    )


def test_a_checked_claim_without_a_mutation_warns(tmp_path):
    data = ledger()
    data["mutations"] = [m for m in data["mutations"] if m["claim"] == "fall-time"]
    audit = full(build(tmp_path, data))
    warned = [r.subject for r in audit.results if r.check == "claims" and r.status == WARN]
    assert warned == ["fall-time-stepped", "energy", "zero-height"]
    assert not audit.failed(strict=False)
    assert audit.failed(strict=True)


def test_a_test_path_outside_the_package_is_refused(tmp_path):
    data = ledger()
    claim(data, "energy")["test"] = "../outside.test.py"
    (tmp_path / "outside.test.py").write_text("assert True\n", encoding="utf-8")
    audit = static(build(tmp_path, data))
    assert "energy: test file ../outside.test.py does not exist" in details(audit, "claims")


# references


@pytest.mark.parametrize(
    ("header", "problem"),
    [
        ("# Fetched 2026-11-13\n", "no source URL"),
        ("# Source: https://example.org/t\n", "no fetch date"),
        ("# Source: ftp://example.org/t, 2026-11-13\n", "no source URL"),
        ("#\n" * 45 + "# https://example.org/t 2026-11-13\n", "no source URL; no fetch date"),
    ],
)
def test_a_reference_without_provenance_in_its_header_fails(tmp_path, header, problem):
    table = header + "5.0 1.0098\n20.0 2.0196\n"
    audit = static(build(tmp_path, **{"test/reference/drop.txt": table}))
    assert problem in details(audit, "references")


def test_a_plain_http_source_is_accepted(tmp_path):
    table = "# http://example.org/t fetched 2026-11-13\n" + read("test/reference/drop.txt")
    table = table.replace("https://physics.nist.gov/cgi-bin/cuu/Value?gn", "(see above)")
    assert "https://" not in table
    audit = static(build(tmp_path, **{"test/reference/drop.txt": table}))
    assert "drop-table: test/reference/drop.txt: sourced, dated and read" in details(
        audit, "references", PASS
    )


def test_a_reference_no_test_reads_fails(tmp_path):
    source = read("test/fall.test.py")
    opened = 'open("test/reference/drop.txt", encoding="utf-8")'
    assert opened in source
    retyped = source.replace(opened, 'open("README.md", encoding="utf-8")')
    audit = static(build(tmp_path / "plain", **{"test/fall.test.py": retyped}))
    assert "drop-table: no test reads it" in details(audit, "references")

    commented = retyped + "# numbers typed from drop.txt\n"
    audit = static(build(tmp_path / "comment", **{"test/fall.test.py": commented}))
    assert "drop-table: no test reads it" in details(audit, "references")

    note = "see drop.txt\n"
    audit = static(
        build(tmp_path / "data", **{"test/fall.test.py": retyped, "test/reference/notes.txt": note})
    )
    assert "drop-table: no test reads it" in details(audit, "references")


def test_a_helper_beside_the_tests_may_read_the_reference(tmp_path):
    source = read("test/fall.test.py")
    helped = source.replace('open("test/reference/drop.txt", encoding="utf-8")', "load_table()")
    helped = helped.replace("from model import", "from loader import load_table\nfrom model import")
    helped = helped.replace('sys.path.insert(0, "src")', 'sys.path[:0] = ["src", "test"]')
    assert helped.count("load_table") == 2 and '["src", "test"]' in helped
    loader = 'def load_table():\n    return open("test/reference/drop.txt", encoding="utf-8")\n'
    audit = full(build(tmp_path, **{"test/fall.test.py": helped, "test/loader.py": loader}))
    assert "drop-table: test/reference/drop.txt: sourced, dated and read" in details(
        audit, "references"
    )
    assert not audit.failed(strict=True), sim_audit.render(audit, True)


def test_reference_bookkeeping_errors_fail(tmp_path):
    data = ledger()
    data["references"].append({"id": "spare", "path": "test/reference/drop.txt"})
    data["references"].append({"id": "gone", "path": "test/reference/gone.txt"})
    data["references"].append({"id": "outside", "path": "../drop.txt"})
    (tmp_path / "drop.txt").write_text(read("test/reference/drop.txt"), encoding="utf-8")
    claim(data, "fall-time")["reference"] = "typo"
    text = details(static(build(tmp_path, data)), "references")
    assert "fall-time: names unknown reference 'typo'" in text
    assert "spare: no claim uses it" in text
    assert "gone: test/reference/gone.txt does not exist in the package" in text
    assert "outside: ../drop.txt does not exist in the package" in text


def test_a_reference_claim_may_cite_a_source_instead_of_a_stored_table(tmp_path):
    data = ledger()
    data["claims"].append(
        {
            "id": "g",
            "kind": "reference",
            "statement": "g is the standard value.",
            "test": "test/fall.test.py",
            "source": "CODATA, standard acceleration of gravity",
        }
    )
    audit = static(build(tmp_path / "cited", data))
    assert "g: cited: CODATA, standard acceleration of gravity" in details(audit, "references")
    data["claims"][-1]["source"] = " "
    audit = static(build(tmp_path / "blank", data))
    assert "g: a reference claim needs `reference`" in details(audit, "references")


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
    assert message in details(audit, "coverage")


def test_a_conservation_claim_is_not_an_anchor(tmp_path):
    data = ledger()
    for entry in data["claims"]:
        if entry["kind"] in {"reference", "independent"}:
            entry["kind"] = "conservation"
            entry.pop("reference", None)
    data["references"] = []
    assert "no anchor outside the model" in details(static(build(tmp_path, data)), "coverage")


# quoted


def test_a_quoted_value_missing_from_the_docs_fails(tmp_path):
    audit = static(build(tmp_path, **{"README.md": "A body falls. It lands at 9.90 m/s.\n"}))
    assert "fall-time: '1.010 s' is in the ledger but not in the docs" in details(audit, "quoted")


def test_a_missing_doc_fails(tmp_path):
    data = ledger()
    data["docs"] = ["README.md", "docs/absent.md"]
    assert "doc docs/absent.md does not exist" in failures(static(build(tmp_path, data)), "quoted")


def test_report_command_failures_fail(tmp_path):
    crashing = build(tmp_path / "crash", **{"tools/report.py": "raise SystemExit(3)\n"})
    audit = sim_audit.audit_package(crashing, run_report=True)
    assert "report command exited 3" in details(audit, "quoted")

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
    assert "fall-time: '1.010 s' is not in the report output" in details(audit, "quoted")


@pytest.mark.parametrize("quoted", [[9.999], ["1.010 s", 9.999], [""], "1.010 s"])
def test_quoted_values_must_be_non_empty_strings(tmp_path, quoted):
    data = ledger()
    claim(data, "fall-time")["quoted"] = quoted
    audit = static(build(tmp_path, data))
    assert "fall-time: `quoted` must be a list of non-empty strings" in details(audit, "ledger")
    assert audit.failed(strict=False)


def test_no_quoted_values_warns(tmp_path):
    data = ledger()
    for entry in data["claims"]:
        entry.pop("quoted", None)
    assert statuses(static(build(tmp_path, data)), "quoted") == [WARN]


# mutations


def test_a_surviving_mutation_fails(tmp_path):
    weak = read("test/fall.test.py").replace("< 1e-9 * G * height", "< 1.0 * G * height")
    audit = full(build(tmp_path, **{"test/fall.test.py": weak}))
    assert audit.failed(strict=False)
    text = details(audit, "mutations")
    assert "faster-impact: SURVIVED" in text
    assert "weaker-gravity: killed" in text


def test_the_package_is_never_touched(tmp_path):
    marker = tmp_path / "live-changed"
    package = build(tmp_path)
    live_model = package / "src" / "model.py"
    spy = (
        read("test/fall.test.py")
        + f"\nif 'G = 9.80665' not in open({str(live_model)!r}).read():\n"
        + f"    open({str(marker)!r}, 'w').write('changed')\n"
    )
    (package / "test" / "fall.test.py").write_text(spy, encoding="utf-8")
    before = {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}
    audit = full(package)
    assert "weaker-gravity: killed" in details(audit, "mutations")
    assert not marker.exists()
    assert before == {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}


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
    text = details(full(build(tmp_path, data)), "mutations")
    assert "never-instant: killed" in text
    assert "harmless: SURVIVED" in text


def test_a_mutations_own_command_is_used(tmp_path):
    data = ledger()
    mutation(data, "weaker-gravity")["command"] = f"{PY} -c pass"
    text = details(full(build(tmp_path, data)), "mutations")
    assert "weaker-gravity: SURVIVED" in text
    assert "never-instant: killed" in text


def test_a_same_length_mutation_is_not_hidden_by_cached_bytecode(tmp_path):
    data = ledger()
    mutation(data, "weaker-gravity")["replace"] = "G = 9.70665"
    assert "weaker-gravity: killed" in details(full(build(tmp_path, data)), "mutations")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        ({"find": "G = 1.62"}, "`find` occurs 0 times in src/model.py"),
        ({"find": "height"}, "it must occur once"),
        ({"file": "src/absent.py"}, "src/absent.py does not exist in the package"),
        ({"file": "../model.py"}, "../model.py does not exist in the package"),
        ({"file": "test/fall.test.py", "find": "assert len(rows) >= 2"}, "is a test"),
        ({"file": "lib/model.py"}, "is in a linked directory"),
    ],
)
def test_a_mutation_that_cannot_be_trusted_fails_without_running(tmp_path, edit, message):
    data = ledger()
    data["link"] = ["lib"]
    mutation(data, "weaker-gravity").update(edit)
    (tmp_path / "model.py").write_text(read("src/model.py"), encoding="utf-8")
    audit = static(build(tmp_path, data, **{"lib/model.py": read("src/model.py")}))
    failed = [r.detail for r in audit.results if r.subject == "weaker-gravity" and r.status == FAIL]
    assert len(failed) == 1 and message in failed[0]


def test_a_mutation_with_no_command_at_all_fails(tmp_path):
    data = ledger()
    del data["commands"]["test"]
    audit = static(build(tmp_path, data))
    assert "weaker-gravity: no `command` and no `commands.test`" in failures(audit, "mutations")
    assert "faster-impact: no `command`" not in details(audit, "mutations")


def test_tests_that_are_red_before_any_change_fail_every_mutation(tmp_path):
    broken = read("test/fall.test.py") + "assert False\n"
    audit = full(build(tmp_path, **{"test/fall.test.py": broken}))
    assert "before any change" in details(audit, "mutations")
    assert PASS not in statuses(audit, "mutations")


def test_a_mutation_that_hangs_is_a_failure_and_leaves_nothing_running(tmp_path):
    pidfile = tmp_path / "pid"
    data = ledger()
    data["mutations"] = [mutation(data, "weaker-gravity")]
    data["mutations"][0]["replace"] = (
        f"import os, time\nopen({str(pidfile)!r}, 'w').write(str(os.getpid()))\n"
        "time.sleep(60)\nG = 9.7"
    )
    data["mutations"][0]["command"] = f"{PY} test/fall.test.py; echo done"
    started = time.monotonic()
    audit = sim_audit.audit_package(build(tmp_path, data), run_mutations=True, timeout=5)
    assert time.monotonic() - started < 30
    assert "weaker-gravity: timed out after 5 s" in failures(audit, "mutations")
    pid = int(pidfile.read_text())
    time.sleep(0.2)
    with pytest.raises(ProcessLookupError):
        os.kill(pid, 0)


def test_no_mutations_fails(tmp_path):
    data = ledger()
    data["mutations"] = []
    audit = static(build(tmp_path, data))
    assert statuses(audit, "mutations") == [FAIL]
    assert "no mutations" in details(audit, "mutations")


# the copy


def test_linked_directories_are_linked_and_caches_are_left_behind(tmp_path):
    package = build(
        tmp_path,
        **{
            "node_modules/big/file.txt": "x",
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
    assert not (target / "absent").exists()
    assert not (target / ".git").exists()
    assert not (target / "src" / "__pycache__").exists()
    assert not (target / ".pytest_cache").exists()
    assert (target / "src" / "model.py").is_file() and not (target / "src").is_symlink()


def test_the_ledgers_link_list_is_used(tmp_path):
    data = ledger()
    data["link"] = ["vendor"]
    probe = (
        read("test/fall.test.py")
        + "\nimport os\nassert os.path.islink('vendor'), 'vendor was copied'\n"
        + "assert not os.path.islink('node_modules'), 'node_modules was linked'\n"
    )
    package = build(
        tmp_path,
        data,
        **{"test/fall.test.py": probe, "vendor/x.txt": "x", "node_modules/y.txt": "y"},
    )
    assert statuses(sim_audit.audit_package(package, run_tests=True), "suite") == [PASS]


# the ledger


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["claims"].append(dict(d["claims"][-1])), "duplicate claim id"),
        (lambda d: d["claims"][-1].update(kind="vibes"), "kind must be one of"),
        (lambda d: d["claims"][-1].update(statement=" "), "a claim needs a `statement`"),
        (lambda d: d["claims"].append({"kind": "omitted"}), "a claim needs a string `id`"),
        (lambda d: d["mutations"][0].update(claim="nope"), "unknown claim"),
        (lambda d: d["mutations"][0].update(replace="G = 9.80665"), "identical"),
        (lambda d: d["mutations"][0].pop("find"), "missing find"),
        (lambda d: d["mutations"][0].update(command=5), "`command` must be a string"),
        (lambda d: d["mutations"].append(dict(d["mutations"][0])), "duplicate mutation id"),
        (lambda d: d["mutations"].append({"claim": "energy"}), "a mutation needs a string `id`"),
        (lambda d: d["references"].append(dict(d["references"][0])), "duplicate reference id"),
        (lambda d: d["references"].append({"id": ["x"], "path": "y"}), "a reference needs"),
    ],
)
def test_malformed_ledger_entries_fail(tmp_path, edit, message):
    data = ledger()
    edit(data)
    audit = static(build(tmp_path, data))
    assert message in details(audit, "ledger")
    assert PASS not in statuses(audit, "ledger")
    assert audit.failed(strict=False)


def test_a_ledger_with_no_claims_fails(tmp_path):
    data = ledger()
    data["claims"], data["mutations"], data["references"] = [], [], []
    assert "the ledger has no valid claims" in failures(static(build(tmp_path, data)), "ledger")


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d.update(commands="x"), "`commands` must map"),
        (lambda d: d.update(commands={"test": 5}), "`commands` must map"),
        (lambda d: d.update(tests=[]), "`tests` must be a mapping"),
        (lambda d: d["tests"].update(dir=5), "`tests.dir` must be a string"),
        (lambda d: d["tests"].update(glob=[5]), "`glob` must be a list"),
        (lambda d: d["tests"].update(assertion="("), "not a regular expression"),
        (lambda d: d["tests"].update(assertion=5), "`tests.assertion` must be a string"),
        (lambda d: d.update(docs=[5]), "`docs` must be a list"),
        (lambda d: d.update(link=["../x"]), "top-level directory names"),
        (lambda d: d.update(link=["sub/node_modules"]), "top-level directory names"),
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


def test_unreadable_and_ambiguous_ledgers_are_refused(tmp_path):
    package = build(tmp_path)
    (package / "sim-claims.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError, match="top level must be a mapping"):
        static(package)
    (package / "sim-claims.json").write_text(json.dumps(ledger()), encoding="utf-8")
    (package / "sim-claims.yaml").write_text("claims: [", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError, match="more than one ledger"):
        static(package)
    (package / "sim-claims.json").unlink()
    with pytest.raises(sim_audit.LedgerError, match="sim-claims.yaml"):
        static(package)
