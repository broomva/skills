"""The fixtures live in a release asset, and the checksum has to mean something.

`fixture_pack.py` is the only thing standing between 20 MB of recorded model output and
a PUBLIC URL, so the properties asserted here are the ones a reviewer would otherwise
have to take on faith: the archive is a function of CONTENT alone, the payload is exactly
the fixtures and not the metadata files that sit beside them, and a manifest that cannot
identify an asset is refused rather than defaulted.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import fixture_pack as P  # noqa: E402


def _tree(root: Path, n: int = 3) -> Path:
    for i in range(1, n + 1):
        d = root / "demo" / "cases" / f"golden-{i:02d}"
        d.mkdir(parents=True)
        (d / "trial-01.jsonl").write_text(json.dumps({"i": i}) + "\n")
        (d / "trial-01.meta.json").write_text(json.dumps({"scrubbed": {}}) + "\n")
    return root


def test_the_archive_is_a_function_of_CONTENT_alone(tmp_path):
    """Two packs of identical fixtures must give an identical sha256, or a re-pack looks
    like a content change and the pinned checksum becomes noise. mtimes, uids and the
    gzip header stamp are all zeroed for this reason."""
    src = _tree(tmp_path / "src")
    a, _, _ = P.build_tarball(src, tmp_path / "a.tar.gz")
    b, _, _ = P.build_tarball(src, tmp_path / "b.tar.gz")
    assert a == b


def test_the_tracked_metadata_files_are_NOT_payload(tmp_path):
    """README.md, MANIFEST.json and BASELINE.json live in the fixture directory and are
    in GIT. Sweeping them into the archive was a real bug and only the SECOND pack could
    reveal it: `pack` writes MANIFEST.json and `baseline --write` writes BASELINE.json,
    so a re-pack included a file the first pack had itself created, and the checksum
    moved for identical fixtures.
    """
    src = _tree(tmp_path / "src")
    for name in P.TRACKED_IN_LIVE_DIR:
        (src / name).write_text("in git, not payload\n")
    members = {str(p.relative_to(src)) for p in P.payload_members(src)}
    assert not (members & set(P.TRACKED_IN_LIVE_DIR)), members
    assert len(members) == 6, members


def test_a_nested_file_with_a_metadata_NAME_is_still_payload(tmp_path):
    """The exclusion is scoped to the directory ROOT. A `README.md` a trial happened to
    write inside a case is recorded output, and dropping it would silently change what
    replay grades."""
    src = _tree(tmp_path / "src", n=1)
    (src / "demo" / "cases" / "golden-01" / "README.md").write_text("recorded\n")
    members = {str(p.relative_to(src)) for p in P.payload_members(src)}
    assert "demo/cases/golden-01/README.md" in members


def test_packing_an_empty_tree_is_refused(tmp_path):
    """An empty archive would fetch, verify, extract, and grade nothing — the vacuous
    green this whole path exists to prevent."""
    (tmp_path / "empty").mkdir()
    with pytest.raises(P.PackError, match="nothing to pack"):
        P.build_tarball(tmp_path / "empty", tmp_path / "out.tar.gz")


@pytest.mark.parametrize("missing", ["asset", "sha256", "url", "release_tag"])
def test_a_manifest_that_cannot_identify_an_asset_is_refused(tmp_path, missing):
    """Never defaulted, never warned about. A manifest with no checksum would make the
    verify step a no-op while still printing a reassuring line."""
    man = {"asset": "a.tar.gz", "sha256": "ab" * 32, "url": "https://x/a.tar.gz",
           "release_tag": "t", "files": 1}
    del man[missing]
    p = tmp_path / "MANIFEST.json"
    p.write_text(json.dumps(man))
    with pytest.raises(P.PackError, match=missing):
        P.load_manifest(p)


def test_an_absent_manifest_says_where_the_fixtures_went(tmp_path):
    """A fresh clone has no fixtures on purpose. The error has to say so, or the next
    person reads it as a broken checkout."""
    with pytest.raises(P.PackError, match="not in git"):
        P.load_manifest(tmp_path / "nope.json")


def test_pack_refuses_a_payload_recorded_with_no_scrub(tmp_path):
    """`--no-scrub` is allowed to exist because debugging a redaction that changed a
    verdict needs it. It is not allowed to reach a public URL, and the meta is what
    makes that enforceable rather than a matter of memory."""
    src = _tree(tmp_path / "src", n=1)
    meta = src / "demo" / "cases" / "golden-01" / "trial-01.meta.json"
    meta.write_text(json.dumps({"scrubbed": False}))
    with pytest.raises(P.PackError, match="--no-scrub"):
        P._check_no_unscrubbed_meta(src)


def test_the_committed_manifest_and_baseline_agree(tmp_path):
    """They are written by two different commands and read by one CI job. A manifest
    listing a skill the baseline does not pin would fetch fixtures nothing asserts."""
    live = REPO / "tests" / "skill_evals" / "fixtures" / "live"
    man = json.loads((live / "MANIFEST.json").read_text())
    base = json.loads((live / "BASELINE.json").read_text())
    assert set(man["skills"]) == set(base["skills"])
    assert base["graded_trials_total"] == sum(
        s["graded_trials"] for s in base["skills"].values())
