#!/usr/bin/env python3
"""fixture_pack — the live fixtures live in a release asset, not in git (BRO-2030).

    python3 scripts/skill_evals/fixture_pack.py pack     # scrub -> audit -> tar -> sha
    python3 scripts/skill_evals/fixture_pack.py fetch    # download, verify, extract
    python3 scripts/skill_evals/fixture_pack.py verify   # checksum an existing tree

WHY THEY ARE NOT IN GIT. 703 files, 20 MB, ~26k lines of recorded model output — per
skill. Five skills is ~35 MB of permanent git objects for data that is regenerated
whenever a description changes, and git history is FOREVER: a fixture pushed to a
public repo stays reachable by SHA even after the branch is deleted. A release asset
is *revocable*. That is the actual property being bought here, and it is worth more
than the repo weight.

WHAT IT DOES **NOT** BUY, and a future maintainer will assume otherwise unless it is
said this plainly:

    A GITHUB RELEASE ASSET ON A PUBLIC REPO IS PUBLICLY DOWNLOADABLE.

There is no token, no gate, no signed URL. Anyone can `curl` it. Moving the fixtures
out of git changed WHERE they are published and made a mistake revocable; it did not
make them private, and it removed no obligation to scrub. The scrub is a precondition
of publishing, not an alternative to it — which is why ``pack`` runs both the scrubber
and the independently-written auditor and refuses to build an archive when either is
unhappy, and why the operator is expected to READ that output before uploading.

The archive is deterministic (sorted entries, zeroed mtimes/uids, fixed gzip mtime), so
the same fixtures produce the same sha256 on any machine. Without that, a re-pack looks
like a content change and the manifest checksum becomes noise.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LIVE_DIR = REPO / "tests" / "skill_evals" / "fixtures" / "live"
MANIFEST = LIVE_DIR / "MANIFEST.json"
DIST = REPO / "dist"

#: Files kept in git inside the fixture directory. Everything else there is payload.
#:
#: BASELINE.json belongs here and was missing, which broke the determinism guarantee in
#: a way only the second pack could show: `pack` writes MANIFEST.json and `baseline
#: --write` writes BASELINE.json, so a re-pack swept the baseline INTO the payload and
#: produced a different sha256 for identical fixtures. A checksum that changes for
#: reasons unrelated to content is a checksum nobody trusts.
TRACKED_IN_LIVE_DIR = frozenset({"README.md", "MANIFEST.json", "BASELINE.json"})

#: The env var a developer sets to replay from a local tarball instead of the network
#: (offline work, or verifying a pack before it is uploaded).
LOCAL_TARBALL_ENV = "SKILL_EVAL_FIXTURES_TARBALL"


class PackError(RuntimeError):
    """Something is wrong with the payload or the asset. Never a warning."""


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def payload_members(root: Path) -> list[Path]:
    """Every payload file under the live dir, sorted. Excludes what git tracks."""
    out = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(root)
        if len(rel.parts) == 1 and rel.name in TRACKED_IN_LIVE_DIR:
            continue
        out.append(p)
    return out


def _run_gate(argv: list[str], label: str) -> None:
    print(f"\n[pack] === {label} ===", flush=True)
    rc = subprocess.run([sys.executable, *argv], cwd=str(REPO)).returncode
    if rc != 0:
        raise PackError(
            f"{label} exited {rc}. Refusing to build an archive from a payload the "
            f"gate is unhappy about — the archive's destination is a public URL."
        )


def _check_no_unscrubbed_meta(root: Path) -> None:
    """A fixture recorded under ``--no-scrub`` must not reach an archive.

    The escape hatch writes ``"scrubbed": false`` into the meta for exactly this: the
    flag is allowed to exist, and it is not allowed to reach publication silently.
    """
    offenders = []
    for meta_path in sorted(root.rglob("trial-*.meta.json")):
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if meta.get("scrubbed") is False:
            offenders.append(str(meta_path.relative_to(root)))
    if offenders:
        raise PackError(
            "these fixtures were recorded with --no-scrub and declare it in their "
            "meta:\n  " + "\n  ".join(offenders[:20]) +
            "\nRe-record them without --no-scrub. Publishing unredacted host output "
            "to a public URL is not a thing this script will do for you."
        )


# ---------------------------------------------------------------------------
# pack
# ---------------------------------------------------------------------------


def build_tarball(root: Path, out_path: Path) -> tuple[str, int, int]:
    """Deterministic .tar.gz of the payload. Returns (sha256, bytes, n_files)."""
    members = payload_members(root)
    if not members:
        raise PackError(f"no payload files under {root} — nothing to pack")

    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as tar:
        for p in members:
            info = tar.gettarinfo(str(p), arcname=str(p.relative_to(root)))
            # Zeroed so the archive is a function of CONTENT only. Otherwise a
            # re-pack of identical fixtures gets a new checksum and the manifest
            # stops meaning anything.
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            info.mode = 0o644
            with open(p, "rb") as fh:
                tar.addfile(info, fh)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "wb") as fh:
        # mtime=0 because gzip stamps the current time by default. filename="" because
        # GzipFile otherwise takes the name from `fileobj.name` and writes it INTO the
        # header — so the archive depended on what you called the output file, and
        # packing the same fixtures to two different paths gave two different
        # checksums. Caught by test_the_archive_is_a_function_of_CONTENT_alone, and not
        # by the two real packs, which happened to use the same output name.
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as gz:
            gz.write(raw.getvalue())
    return _sha256_file(out_path), out_path.stat().st_size, len(members)


def cmd_pack(args: argparse.Namespace) -> int:
    root = args.root
    if not root.is_dir():
        raise PackError(f"no such fixture tree: {root}")

    print("[pack] Publishing is a SEPARATE act from packing, and this script does not")
    print("[pack] do it. It scrubs, audits, and writes an archive plus a checksum; the")
    print("[pack] upload command is printed at the end for a human to run — because the")
    print("[pack] destination is a PUBLIC URL that anyone can download.")

    _run_gate(["scripts/skill_evals/scrub.py", str(root), "--apply"], "scrub --apply")
    _run_gate(["scripts/skill_evals/scrub.py", str(root), "--check"],
              "scrub --check (verify the apply converged)")
    _run_gate(["scripts/skill_evals/fixture_audit.py", str(root)],
              "independent audit (a SECOND blocklist, not proof of absence)")
    _check_no_unscrubbed_meta(root)

    tag = args.tag
    asset = f"{tag}.tar.gz"
    out = DIST / asset
    sha, size, n = build_tarball(root, out)

    manifest = {
        "asset": asset,
        "release_tag": tag,
        "sha256": sha,
        "bytes": size,
        "files": n,
        "skills": sorted(p.name for p in root.iterdir() if p.is_dir()),
        "url": f"https://github.com/{args.repo}/releases/download/{tag}/{asset}",
        "note": (
            "PUBLIC asset. Scrubbed and audited before publication; scrubbing is a "
            "blocklist and fails open. See scripts/skill_evals/scrub.py."
        ),
    }
    if not args.no_manifest:
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")

    print(f"\n[pack] {out}")
    print(f"[pack] sha256  {sha}")
    print(f"[pack] {size:,} bytes, {n} files, skills: {', '.join(manifest['skills'])}")
    if not args.no_manifest:
        print(f"[pack] manifest written: {MANIFEST.relative_to(REPO)}")
    try:
        shown = out.relative_to(REPO)
    except ValueError:
        shown = out
    print("\n[pack] ONE COMMAND FOR THE OPERATOR — read the audit output above first:")
    print(f"\n    gh release create {tag} {shown} \\\n"
          f"      --repo {args.repo} --title 'skill-eval live fixtures ({tag})' \\\n"
          f"      --notes 'Recorded eval transcripts replayed by scripts/skill_evals. "
          f"sha256 {sha}. PUBLIC asset: scrubbed and audited, not private.'\n")
    print("[pack] If the release already exists, upload into it instead:")
    print(f"\n    gh release upload {tag} {shown} --repo {args.repo} --clobber\n")
    return 0


# ---------------------------------------------------------------------------
# fetch / verify
# ---------------------------------------------------------------------------


def load_manifest(path: Path = MANIFEST) -> dict:
    if not path.is_file():
        raise PackError(
            f"no fixture manifest at {path}. The live fixtures are not in git; the "
            "manifest is what names the release asset and pins its checksum. Build one "
            "with `fixture_pack.py pack`."
        )
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise PackError(f"{path} is not valid JSON: {exc}") from exc
    for key in ("asset", "sha256", "url", "release_tag"):
        if not manifest.get(key):
            raise PackError(f"{path} carries no {key!r} — it cannot identify an asset")
    return manifest


def _download(url: str, dest: Path) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "skill-evals-fixture-pack"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as fh:
            shutil.copyfileobj(resp, fh)
    except urllib.error.HTTPError as exc:
        raise PackError(
            f"HTTP {exc.code} fetching the fixture asset:\n  {url}\n\n"
            "THIS IS NOT A REASON TO SKIP THE REPLAY. A replay job that shrugs at a "
            "missing asset reports green having graded nothing, which is the exact "
            "failure this harness exists to catch.\n"
            "If the release has not been published yet, the operator must run the "
            "`gh release create` line printed by `fixture_pack.py pack`."
        ) from exc
    except urllib.error.URLError as exc:
        raise PackError(f"could not reach {url}: {exc.reason}") from exc


def cmd_fetch(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    dest_root = args.into
    tmpdir = Path(tempfile.mkdtemp(prefix="skill-eval-fixtures."))
    try:
        local = os.environ.get(LOCAL_TARBALL_ENV)
        if local:
            src = Path(local)
            if not src.is_file():
                raise PackError(f"{LOCAL_TARBALL_ENV}={local} is not a file")
            print(f"[fetch] local tarball via {LOCAL_TARBALL_ENV}: {src}")
            tarball = src
        else:
            tarball = tmpdir / manifest["asset"]
            print(f"[fetch] {manifest['url']}")
            _download(manifest["url"], tarball)

        actual = _sha256_file(tarball)
        if actual != manifest["sha256"]:
            raise PackError(
                "CHECKSUM MISMATCH — refusing to extract.\n"
                f"  expected  {manifest['sha256']}\n"
                f"  actual    {actual}\n"
                f"  asset     {tarball}\n\n"
                "The asset does not match the manifest this commit pins. Either the "
                "release was replaced without updating the manifest, or the download "
                "is corrupt. Grading fixtures the manifest cannot vouch for would "
                "decouple CI from the recording it claims to replay."
            )
        print(f"[fetch] sha256 OK  {actual}")

        dest_root.mkdir(parents=True, exist_ok=True)
        with tarfile.open(tarball, mode="r:gz") as tar:
            for member in tar.getmembers():
                # Path traversal: the asset is public, so treat it as untrusted input
                # even though we produced it.
                target = (dest_root / member.name).resolve()
                if not str(target).startswith(str(dest_root.resolve()) + os.sep):
                    raise PackError(f"archive member escapes the destination: {member.name}")
                if member.issym() or member.islnk():
                    raise PackError(f"archive contains a link member: {member.name}")
            try:
                # `filter="data"` refuses absolute paths, links and device nodes. The
                # members are validated above too; this is the interpreter's own check,
                # and it is absent before 3.11.4.
                tar.extractall(dest_root, filter="data")
            except TypeError:
                tar.extractall(dest_root)  # noqa: S202 — members validated above
        n = len(payload_members(dest_root))
        print(f"[fetch] extracted {n} file(s) into {dest_root}")
        if n != manifest["files"]:
            raise PackError(
                f"manifest declares {manifest['files']} files, extracted {n}"
            )
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def cmd_verify(args: argparse.Namespace) -> int:
    manifest = load_manifest()
    members = payload_members(args.root)
    print(f"[verify] {len(members)} payload file(s) under {args.root}")
    if not members:
        raise PackError(
            f"{args.root} holds no fixtures. They are not in git — run\n"
            "  python3 scripts/skill_evals/fixture_pack.py fetch"
        )
    if len(members) != manifest["files"]:
        raise PackError(
            f"{len(members)} file(s) on disk, manifest declares {manifest['files']}. "
            "The tree is not the recording this commit pins."
        )
    print(f"[verify] file count matches the manifest ({manifest['files']})")
    print(f"[verify] asset {manifest['asset']}  sha256 {manifest['sha256']}")
    return 0


# ---------------------------------------------------------------------------
# baseline — what makes replaying these fixtures in CI mean anything
# ---------------------------------------------------------------------------

BASELINE = LIVE_DIR / "BASELINE.json"

#: Aggregate fields pinned per skill. Deliberately the whole shape rather than one
#: pass rate: `positive` and `negative` moving in opposite directions is the signature
#: of a grading change, and a single number hides it.
_PINNED = ("trials", "graded_trials", "passes", "errors", "invisible")


def _replay_aggregate(skill: str, case_root: Path) -> dict:
    """Replay one skill's fixtures and return the aggregate, or raise."""
    with tempfile.TemporaryDirectory() as td:
        report = Path(td) / "r.json"
        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts/skill_evals/runner.py"),
             "--skill", skill, "--replay", str(case_root), "--trials", "3",
             # The sweep's own verdict is FAIL for six of seven skills, so the gate here
             # is NOT "exit 0". It is "the numbers are exactly what was recorded".
             # Forgiving the rate and the errors is what lets the run reach the point of
             # reporting them; the zero-graded-trials invariant still cannot be forgiven,
             # so a fixture set that graded nothing still fails.
             "--allow-errors", "--threshold", "0.0",
             "--report", str(report)],
            cwd=str(REPO), capture_output=True, text=True,
        )
        if not report.is_file():
            raise PackError(
                f"replaying {skill} produced no report (exit {proc.returncode}).\n"
                f"{proc.stdout[-2000:]}\n{proc.stderr[-2000:]}"
            )
        agg = json.loads(report.read_text())["aggregate"]
    out = {k: agg[k] for k in _PINNED}
    out["positive"] = {"trials": agg["positive"]["trials"], "passes": agg["positive"]["passes"]}
    out["negative"] = {"trials": agg["negative"]["trials"], "passes": agg["negative"]["passes"]}
    return out


def cmd_baseline(args: argparse.Namespace) -> int:
    """Pin every recorded number, so replaying the asset in CI is not decoration.

    Fetching fixtures and replaying them proves nothing on its own when the recorded
    verdict is FAIL — `--threshold 0.0` would green anything. What makes the job real is
    that these exact aggregates are asserted: 351 graded trials, and every pass count.
    A description edit turns the fixtures STALE and the replay RED before it gets here;
    a grading change moves a number and gets caught here.
    """
    root = args.root
    skills = sorted(p.name for p in root.iterdir() if p.is_dir()) if root.is_dir() else []
    if not skills:
        raise PackError(
            f"no fixture sets under {root}. They are not in git — run\n"
            "  python3 scripts/skill_evals/fixture_pack.py fetch"
        )

    measured = {s: _replay_aggregate(s, root / s) for s in skills}
    total = sum(m["graded_trials"] for m in measured.values())

    if args.write:
        BASELINE.write_text(json.dumps(
            {"recorded_at_sweep": args.sweep, "graded_trials_total": total,
             "skills": measured}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"[baseline] wrote {BASELINE.relative_to(REPO)} — {total} graded trials")
        return 0

    if not BASELINE.is_file():
        raise PackError(f"no baseline at {BASELINE}. Write one with `baseline --write`.")
    expected = json.loads(BASELINE.read_text())
    drift = []
    for skill in sorted(set(expected["skills"]) | set(measured)):
        want, got = expected["skills"].get(skill), measured.get(skill)
        if want != got:
            drift.append(f"  {skill}\n    pinned   {json.dumps(want, sort_keys=True)}\n"
                         f"    measured {json.dumps(got, sort_keys=True)}")
    if drift:
        raise PackError(
            "REPLAY DRIFT — the fetched fixtures do not grade to the pinned numbers:\n"
            + "\n".join(drift) +
            "\n\nEither the asset is not the recording this commit pins, or the harness's "
            "grading changed. Both are real; neither is a number to update without "
            "saying which it was."
        )
    print(f"[baseline] {len(measured)} skill(s), {total} graded trials — "
          "every pinned aggregate matches")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("pack", help="scrub, audit, and build the release asset")
    p.add_argument("--root", type=Path, default=LIVE_DIR)
    # DATED, and deliberately without a `-vX.Y.Z` suffix: `release-skill.yml` fires on
    # `*-v[0-9]+.[0-9]+.[0-9]+` and would try to resolve `<that>` as a SKILL and fail
    # the push. A date also says what the tag means — fixtures are a RECORDING, and the
    # next sweep gets its own tag rather than silently replacing this one.
    p.add_argument("--tag", default="skill-eval-fixtures-2026-07-29",
                   help="release tag the asset will live under (no -vX.Y.Z: that "
                        "pattern triggers release-skill.yml)")
    p.add_argument("--repo", default="broomva/skills")
    p.add_argument("--no-manifest", action="store_true",
                   help="do not rewrite MANIFEST.json (checksum-only dry run)")
    p.set_defaults(func=cmd_pack)

    p = sub.add_parser("fetch", help="download + verify + extract the asset")
    p.add_argument("--into", type=Path, default=LIVE_DIR)
    p.set_defaults(func=cmd_fetch)

    p = sub.add_parser("verify", help="check an extracted tree against the manifest")
    p.add_argument("--root", type=Path, default=LIVE_DIR)
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("baseline", help="assert the fixtures still grade to the "
                                        "recorded numbers (what CI runs)")
    p.add_argument("--root", type=Path, default=LIVE_DIR)
    p.add_argument("--write", action="store_true", help="(re)pin the current numbers")
    p.add_argument("--sweep", default="2026-07-29", help="sweep date, for --write")
    p.set_defaults(func=cmd_baseline)

    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except PackError as exc:
        print(f"\n[fixture-pack] FAIL — {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
