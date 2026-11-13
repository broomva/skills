"""Tests for sim_audit.py.

Each test builds a tiny simulation package (a falling body) in a temp directory,
breaks one thing, and checks that the audit names it. The package's commands are
run with the interpreter running these tests, so nothing else is needed.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import sim_audit  # noqa: E402

PY = sys.executable

MODEL = """\
G = 9.81


def fall_time(height):
    return (2 * height / G) ** 0.5


def speed(height):
    return G * fall_time(height)
"""

TEST = """\
import sys
sys.path.insert(0, 'src')
from model import fall_time, speed

rows = [l.split() for l in open('test/reference/drop.txt') if not l.startswith('#')]
for height, seconds in rows:
    assert abs(fall_time(float(height)) - float(seconds)) < 0.01, height
assert abs(speed(5.0) ** 2 / 2 - 9.81 * 5.0) < 1e-9
assert fall_time(0.0) == 0.0
"""

REFERENCE = """\
# Fall times from rest, vacuum.
# Source: https://example.org/drop-table
# Fetched: 2026-11-13
5.0 1.0096
20.0 2.0193
"""

REPORT = """\
import sys
sys.path.insert(0, 'src')
from model import fall_time
print(f'fall time from 5 m: {fall_time(5.0):.3f} s')
"""

README = "A body falls 5 m in 1.010 s. Air drag is left out.\n"


def ledger() -> dict:
    return {
        "docs": ["README.md"],
        "tests": {"dir": "test", "glob": "*.test.py"},
        "commands": {
            "test": f"{PY} test/fall.test.py",
            "report": f"{PY} tools/report.py",
        },
        "references": [{"id": "drop", "path": "test/reference/drop.txt"}],
        "claims": [
            {
                "id": "fall-time",
                "kind": "reference",
                "statement": "Fall time matches the table.",
                "test": "test/fall.test.py",
                "reference": "drop",
                "quoted": ["1.010 s"],
            },
            {
                "id": "energy",
                "kind": "conservation",
                "statement": "Kinetic energy at the ground equals the potential energy lost.",
                "test": "test/fall.test.py",
            },
            {
                "id": "no-height",
                "kind": "control",
                "statement": "From zero height the fall takes no time.",
                "test": "test/fall.test.py",
            },
            {"id": "no-drag", "kind": "omitted", "statement": "Air drag."},
        ],
        "mutations": [
            {
                "id": "halve-g",
                "claim": "fall-time",
                "file": "src/model.py",
                "find": "G = 9.81",
                "replace": "G = 4.9",
            }
        ],
    }


def build(root: Path, data: dict | None = None, **files: str) -> Path:
    package = root / "pkg"
    contents = {
        "src/model.py": MODEL,
        "test/fall.test.py": TEST,
        "test/reference/drop.txt": REFERENCE,
        "tools/report.py": REPORT,
        "README.md": README,
        **files,
    }
    for name, text in contents.items():
        path = package / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    (package / "sim-claims.json").write_text(
        json.dumps(ledger() if data is None else data), encoding="utf-8"
    )
    return package


def statuses(audit: sim_audit.Audit, check: str) -> list[str]:
    return [r.status for r in audit.results if r.check == check]


def details(audit: sim_audit.Audit, check: str) -> str:
    return " | ".join(f"{r.subject}: {r.detail}" for r in audit.results if r.check == check)


def full(package: Path) -> sim_audit.Audit:
    return sim_audit.audit_package(package, run_report=True, run_mutations=True, timeout=60)


# The clean package


def test_clean_package_passes_every_check(tmp_path):
    audit = full(build(tmp_path))
    assert not audit.failed(strict=False), sim_audit.render(audit, False)
    for check in ("ledger", "asserting", "references", "coverage", "quoted", "mutations"):
        assert sim_audit.PASS in statuses(audit, check), check


def test_main_exit_codes(tmp_path, capsys):
    package = build(tmp_path)
    assert sim_audit.main([str(package), "--run-report", "--run-mutations"]) == 0
    assert sim_audit.main([str(tmp_path / "missing")]) == 2
    (tmp_path / "empty").mkdir()
    assert sim_audit.main([str(tmp_path / "empty")]) == 2
    capsys.readouterr()


def test_json_output_is_machine_readable(tmp_path, capsys):
    package = build(tmp_path)
    assert sim_audit.main([str(package), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is True
    assert {r["check"] for r in payload["results"]} >= {"ledger", "asserting", "mutations"}


# Flags not given report SKIP, never PASS


def test_without_flags_the_runs_are_skipped_not_passed(tmp_path):
    audit = sim_audit.audit_package(build(tmp_path))
    assert sim_audit.SKIP in statuses(audit, "quoted")
    assert statuses(audit, "mutations") == [sim_audit.SKIP]


def test_a_wrong_number_passes_without_the_report_and_fails_with_it(tmp_path):
    data = ledger()
    data["claims"][0]["quoted"] = ["1.234 s"]
    package = build(tmp_path, data, **{"README.md": "A body falls 5 m in 1.234 s.\n"})
    assert not sim_audit.audit_package(package).failed(strict=False)
    audit = sim_audit.audit_package(package, run_report=True)
    assert audit.failed(strict=False)
    assert "not in the report output" in details(audit, "quoted")


# asserting


def test_a_test_file_that_only_prints_fails(tmp_path):
    printing = "import sys\nsys.path.insert(0, 'src')\nfrom model import fall_time\nprint(fall_time(5.0))\n"
    audit = sim_audit.audit_package(build(tmp_path, **{"test/print.test.py": printing}))
    assert sim_audit.FAIL in statuses(audit, "asserting")
    assert "print.test.py" in details(audit, "asserting")


def test_a_commented_out_assertion_does_not_count(tmp_path):
    commented = "x = 1\n# assert x == 2\nprint(x)  // expect(x).toBe(2)\n/* assert(x) */\n"
    audit = sim_audit.audit_package(build(tmp_path, **{"test/quiet.test.py": commented}))
    assert "quiet.test.py" in details(audit, "asserting")


@pytest.mark.parametrize(
    "line",
    [
        "expect(range).toBeCloseTo(4.16, 2)",
        "assert abs(x - 1) < 0.01",
        "assert_eq!(a, b);",
        "EXPECT_NEAR(a, b, 1e-6);",
        "t.Fatalf(\"got %v\", x)",
        "if (bad) process.exit(1)",
        "if (bad) throw new Error('range')",
        "raise AssertionError('range')",
        "with pytest.raises(ValueError):",
    ],
)
def test_assertion_constructs_are_recognised(tmp_path, line):
    path = tmp_path / "t.txt"
    path.write_text(f"setup()\n{line}\n", encoding="utf-8")
    assert sim_audit.has_assertion(path)


@pytest.mark.parametrize(
    "line",
    ["console.log(range)", "print(f'{x:.3f}')", "process.exit(0)", "const url = 'https://x.org/a'"],
)
def test_non_assertions_are_not_recognised(tmp_path, line):
    path = tmp_path / "t.txt"
    path.write_text(f"{line}\n", encoding="utf-8")
    assert not sim_audit.has_assertion(path)


def test_no_test_files_at_all_fails(tmp_path):
    data = ledger()
    data["tests"] = {"dir": "nowhere"}
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert statuses(audit, "asserting") == [sim_audit.FAIL]


# claims


def test_a_checked_claim_needs_an_existing_asserting_test(tmp_path):
    data = ledger()
    data["claims"][1]["test"] = "test/absent.test.py"
    del data["claims"][2]["test"]
    audit = sim_audit.audit_package(build(tmp_path, data))
    text = details(audit, "claims")
    assert "energy: test file test/absent.test.py does not exist" in text
    assert "no-height: a control claim needs a `test` file" in text


def test_a_checked_claim_without_a_mutation_warns_and_strict_fails_it(tmp_path):
    audit = full(build(tmp_path))
    warned = [r.subject for r in audit.results if r.check == "claims" and r.status == sim_audit.WARN]
    assert warned == ["energy", "no-height"]
    assert not audit.failed(strict=False)
    assert audit.failed(strict=True)


def test_a_test_path_outside_the_package_is_refused(tmp_path):
    data = ledger()
    data["claims"][1]["test"] = "../outside.py"
    (tmp_path / "outside.py").write_text("assert True\n", encoding="utf-8")
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert "energy: test file ../outside.py does not exist" in details(audit, "claims")


# references


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("# Fetched: 2026-11-13\n5.0 1.0096\n", "no source URL"),
        ("# Source: https://example.org/t\n5.0 1.0096\n", "no fetch date"),
    ],
)
def test_a_reference_without_provenance_fails(tmp_path, text, problem):
    audit = sim_audit.audit_package(build(tmp_path, **{"test/reference/drop.txt": text}))
    assert problem in details(audit, "references")


def test_a_reference_no_test_reads_fails(tmp_path):
    retyped = TEST.replace(
        "rows = [l.split() for l in open('test/reference/drop.txt') if not l.startswith('#')]",
        "rows = [('5.0', '1.0096')]",
    )
    audit = sim_audit.audit_package(build(tmp_path, **{"test/fall.test.py": retyped}))
    assert "no test reads it" in details(audit, "references")


def test_a_reference_no_claim_uses_and_an_unknown_reference_fail(tmp_path):
    data = ledger()
    data["references"].append({"id": "spare", "path": "test/reference/drop.txt"})
    data["claims"][0]["reference"] = "typo"
    audit = sim_audit.audit_package(build(tmp_path, data))
    text = details(audit, "references")
    assert "fall-time: names unknown reference 'typo'" in text
    assert "spare: no claim uses it" in text


def test_a_reference_claim_may_cite_a_source_instead_of_a_stored_table(tmp_path):
    data = ledger()
    data["claims"].append(
        {
            "id": "g",
            "kind": "reference",
            "statement": "g at sea level.",
            "test": "test/fall.test.py",
            "source": "CODATA 2018, standard acceleration of gravity",
        }
    )
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert "g: cited: CODATA 2018" in details(audit, "references")
    data["claims"][-1]["source"] = " "
    audit = sim_audit.audit_package(build(tmp_path / "second", data))
    assert "g: a reference claim needs `reference`" in details(audit, "references")


# coverage


@pytest.mark.parametrize(
    ("drop", "message"),
    [
        ("no-height", "no negative control"),
        ("fall-time", "no anchor outside the model"),
        ("no-drag", "no stated limit"),
    ],
)
def test_each_missing_kind_of_claim_fails_coverage(tmp_path, drop, message):
    data = ledger()
    data["claims"] = [c for c in data["claims"] if c["id"] != drop]
    data["mutations"] = [m for m in data["mutations"] if m["claim"] != drop]
    data["references"] = [] if drop == "fall-time" else data["references"]
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert message in details(audit, "coverage")


# quoted


def test_a_quoted_value_missing_from_the_docs_fails(tmp_path):
    audit = sim_audit.audit_package(build(tmp_path, **{"README.md": "A body falls.\n"}))
    assert "'1.010 s' is in the ledger but not in the docs" in details(audit, "quoted")


def test_a_failing_report_command_fails(tmp_path):
    audit = sim_audit.audit_package(
        build(tmp_path, **{"tools/report.py": "raise SystemExit(3)\n"}), run_report=True
    )
    assert "report command exited 3" in details(audit, "quoted")


def test_no_quoted_values_warns(tmp_path):
    data = ledger()
    del data["claims"][0]["quoted"]
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert statuses(audit, "quoted") == [sim_audit.WARN]


# mutations


def test_a_surviving_mutation_fails(tmp_path):
    weak = "import sys\nsys.path.insert(0, 'src')\nfrom model import fall_time\nassert fall_time(5.0) > 0\n"
    weak += "open('test/reference/drop.txt')\n"
    audit = full(build(tmp_path, **{"test/fall.test.py": weak}))
    assert audit.failed(strict=False)
    assert "SURVIVED" in details(audit, "mutations")


def test_a_killed_mutation_passes_and_the_package_is_untouched(tmp_path):
    package = build(tmp_path)
    before = {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}
    audit = full(package)
    assert "halve-g: killed" in details(audit, "mutations")
    after = {p: p.read_bytes() for p in package.rglob("*") if p.is_file()}
    assert before == after


def test_a_same_length_mutation_is_not_hidden_by_cached_bytecode(tmp_path):
    data = ledger()
    data["mutations"][0]["replace"] = "G = 1.62"
    audit = full(build(tmp_path, data))
    assert "halve-g: killed" in details(audit, "mutations")


def test_a_stale_mutation_fails_without_running(tmp_path):
    data = ledger()
    data["mutations"][0]["find"] = "G = 1.62"
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert "`find` occurs 0 times" in details(audit, "mutations")


def test_an_ambiguous_mutation_fails(tmp_path):
    data = ledger()
    data["mutations"][0]["find"] = "height"
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert "it must occur once" in details(audit, "mutations")


def test_tests_that_are_red_before_any_change_fail_the_mutation(tmp_path):
    broken = TEST + "assert False\n"
    audit = full(build(tmp_path, **{"test/fall.test.py": broken}))
    assert "before any change" in details(audit, "mutations")


def test_a_mutation_that_hangs_is_a_failure(tmp_path):
    data = ledger()
    data["mutations"][0]["replace"] = "import time\ntime.sleep(30)\nG = 9.81"
    data["mutations"][0]["command"] = f"{PY} test/fall.test.py"
    package = build(tmp_path, data)
    audit = sim_audit.audit_package(package, run_mutations=True, timeout=3)
    assert "timed out" in details(audit, "mutations")


def test_no_mutations_warns(tmp_path):
    data = ledger()
    data["mutations"] = []
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert statuses(audit, "mutations") == [sim_audit.WARN]


def test_linked_directories_are_linked_not_copied(tmp_path):
    package = build(tmp_path, **{"node_modules/big/file.txt": "x"})
    copy = tmp_path / "copy"
    sim_audit.copy_package(package, copy, sim_audit.DEFAULT_LINKS)
    assert (copy / "node_modules").is_symlink()
    assert (copy / "src" / "model.py").is_file() and not (copy / "src").is_symlink()


# ledger


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (lambda d: d["claims"].append(dict(d["claims"][3])), "duplicate claim id"),
        (lambda d: d["claims"][3].update(kind="vibes"), "kind must be one of"),
        (lambda d: d["claims"][3].update(statement=" "), "a claim needs a `statement`"),
        (lambda d: d["mutations"][0].update(claim="nope"), "unknown claim"),
        (lambda d: d["mutations"][0].update(replace="G = 9.81"), "identical"),
        (lambda d: d["mutations"][0].pop("find"), "missing find"),
        (lambda d: d["references"].append({"id": "drop", "path": "x"}), "duplicate reference id"),
    ],
)
def test_malformed_ledger_entries_fail(tmp_path, edit, message):
    data = ledger()
    edit(data)
    audit = sim_audit.audit_package(build(tmp_path, data))
    assert message in details(audit, "ledger")
    assert audit.failed(strict=False)


def test_unreadable_ledgers_raise(tmp_path):
    package = build(tmp_path)
    (package / "sim-claims.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError):
        sim_audit.audit_package(package)
    (package / "sim-claims.json").write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(sim_audit.LedgerError):
        sim_audit.audit_package(package)


def test_a_yaml_ledger_is_read(tmp_path):
    yaml = pytest.importorskip("yaml")
    package = build(tmp_path)
    (package / "sim-claims.json").unlink()
    (package / "sim-claims.yaml").write_text(yaml.safe_dump(ledger()), encoding="utf-8")
    assert not full(package).failed(strict=False)


def test_the_shipped_template_is_a_valid_ledger_shape():
    yaml = pytest.importorskip("yaml")
    template = Path(__file__).resolve().parents[1] / "assets" / "templates" / "sim-claims.yaml"
    data = yaml.safe_load(template.read_text(encoding="utf-8"))
    audit = sim_audit.Audit()
    _, claims, mutations = sim_audit.check_ledger(data, audit)
    assert statuses(audit, "ledger") == [sim_audit.PASS]
    assert {c["kind"] for c in claims} == set(sim_audit.KINDS)
    assert mutations
    sim_audit.check_coverage(claims, audit)
    assert statuses(audit, "coverage") == [sim_audit.PASS]
