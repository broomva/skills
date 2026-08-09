#!/usr/bin/env python3
"""Safely materialize and verify the Broomva design system."""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


SKILL_DIR = Path(__file__).resolve().parent.parent
DESIGN_SOURCE = SKILL_DIR / "DESIGN.md"
SYSTEM_SOURCE = SKILL_DIR / "assets" / "system"
SYSTEM_DEST = Path("design-system") / "broomva"
PROFILES = ("essentials", "tokens", "full")

ESSENTIALS = {
    "broomva-essentials.css",
    "assets/broomva-blackhole-logo.png",
}
TOKEN_FILES = ESSENTIALS | {
    "styles.css",
    "manifest.json",
    "adherence.oxlintrc.json",
}
TOKEN_PREFIXES = ("tokens/", "fonts/")


class ReferenceParser(HTMLParser):
    """Collect local browser references without executing source artifacts."""

    def __init__(self) -> None:
        super().__init__()
        self.references: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del tag
        for key, value in attrs:
            if key in {"href", "src"} and value:
                self.references.append(value)


def local_path(source: Path, reference: str) -> Path | None:
    parsed = urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
        return None
    return (source.parent / parsed.path).resolve(strict=False)


def local_reference_errors() -> list[str]:
    errors: list[str] = []
    root = SYSTEM_SOURCE.resolve()

    for html in SYSTEM_SOURCE.rglob("*.html"):
        parser = ReferenceParser()
        parser.feed(html.read_text(encoding="utf-8", errors="replace"))
        for reference in parser.references:
            target = local_path(html, reference)
            if target is None:
                continue
            if root not in target.parents and target != root:
                errors.append(f"HTML reference escapes system: {html.name} -> {reference}")
            elif not target.exists():
                errors.append(
                    f"missing HTML reference: {html.relative_to(SYSTEM_SOURCE)} -> {reference}"
                )

    css_reference = re.compile(r"url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")
    for css in SYSTEM_SOURCE.rglob("*.css"):
        for _, reference in css_reference.findall(css.read_text(encoding="utf-8")):
            target = local_path(css, reference)
            if target is not None and not target.exists():
                errors.append(
                    f"missing CSS reference: {css.relative_to(SYSTEM_SOURCE)} -> {reference}"
                )

    jsx_reference = re.compile(r"(?:src|href)\s*=\s*(['\"])([^'\"]+)\1")
    for source in SYSTEM_SOURCE.rglob("*.jsx"):
        for _, reference in jsx_reference.findall(source.read_text(encoding="utf-8")):
            target = local_path(source, reference)
            if target is not None and not target.exists():
                errors.append(
                    f"missing JSX reference: {source.relative_to(SYSTEM_SOURCE)} -> {reference}"
                )
    return errors


class MaterializeError(RuntimeError):
    """An expected, user-actionable materialization error."""


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def source_files(profile: str) -> list[Path]:
    if profile not in PROFILES:
        raise MaterializeError(f"unknown profile: {profile}")
    files = [path for path in SYSTEM_SOURCE.rglob("*") if path.is_file()]
    if profile == "full":
        return sorted(files)

    selected: list[Path] = []
    for path in files:
        relative = path.relative_to(SYSTEM_SOURCE).as_posix()
        if relative in ESSENTIALS:
            selected.append(path)
        elif profile == "tokens" and (
            relative in TOKEN_FILES or relative.startswith(TOKEN_PREFIXES)
        ):
            selected.append(path)
    return sorted(selected)


def copy_plan(target: Path, profile: str) -> list[tuple[Path, Path]]:
    plan = [(DESIGN_SOURCE, target / "DESIGN.md")]
    plan.extend(
        (source, target / SYSTEM_DEST / source.relative_to(SYSTEM_SOURCE))
        for source in source_files(profile)
    )
    return plan


def ensure_within(path: Path, root: Path, label: str) -> None:
    resolved = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise MaterializeError(f"{label} escapes target root: {path}")


def validate_source() -> list[str]:
    errors: list[str] = []
    if not DESIGN_SOURCE.is_file():
        errors.append("missing DESIGN.md")
    else:
        design = DESIGN_SOURCE.read_text(encoding="utf-8")
        for section in range(1, 7):
            if f"## {section}." not in design:
                errors.append(f"DESIGN.md missing section {section}")
        for phrase in ("Blue-black ink", "Undertow", "Needs you", "prefers-reduced-motion"):
            if phrase not in design:
                errors.append(f"DESIGN.md missing canonical phrase: {phrase}")

    required = {
        "_ds_bundle.js": "BroomvaDesignSystem_5727d9",
        "index.js": "export { Button }",
        "readme.md": "Broomva Design System",
        "broomva-look-spec.md": "Broomva look",
        "tokens/colors.css": "--bv-ink:",
        "tokens/typography.css": "--bv-font-sans:",
        "tokens/spacing.css": "--bv-space-1:",
        "tokens/glass.css": "Glass is EARNED",
        "tokens/motion.css": "prefers-reduced-motion",
        "fonts/OFL.txt": "SIL OPEN FONT LICENSE Version 1.1",
    }
    for relative, anchor in required.items():
        path = SYSTEM_SOURCE / relative
        if not path.is_file():
            errors.append(f"missing asset: {relative}")
            continue
        if anchor not in path.read_text(encoding="utf-8", errors="replace"):
            errors.append(f"asset {relative} missing anchor: {anchor}")

    manifest_path = SYSTEM_SOURCE / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        exports = manifest.get("components", [])
        if len(exports) != 31:
            errors.append(f"manifest declares {len(exports)} components, expected 31")
        if manifest.get("namespace") != "BroomvaDesignSystem_5727d9":
            errors.append("manifest namespace changed")
        declared_paths = [item.get("sourcePath") for item in exports]
        declared_paths += [item.get("path") for item in manifest.get("cards", [])]
        declared_paths += manifest.get("globalCssPaths", [])
        for template in manifest.get("templates", []):
            declared_paths.extend(
                [template.get("entryPath"), template.get("thumbnail", {}).get("path")]
            )
        for font in manifest.get("fonts", []):
            declared_paths.extend(font.get("files", []))
        for relative in filter(None, declared_paths):
            if not (SYSTEM_SOURCE / relative).exists():
                errors.append(f"manifest target missing: {relative}")

        index = (SYSTEM_SOURCE / "index.js").read_text(encoding="utf-8")
        public_names = set(re.findall(r"\b[A-Z][A-Za-z]+\b(?=[, }])", index))
        expected_names = {item["name"] for item in exports}
        missing_exports = sorted(expected_names - public_names)
        if missing_exports:
            errors.append("index.js missing exports: " + ", ".join(missing_exports))
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"invalid manifest.json: {exc}")

    errors.extend(local_reference_errors())

    checksum_path = SYSTEM_SOURCE / "SHA256SUMS"
    try:
        expected_hashes: dict[str, str] = {}
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            checksum, relative = line.split(maxsplit=1)
            expected_hashes[relative.removeprefix("./")] = checksum
        actual_paths = {
            path.relative_to(SYSTEM_SOURCE).as_posix()
            for path in SYSTEM_SOURCE.rglob("*")
            if path.is_file() and path != checksum_path
        }
        if set(expected_hashes) != actual_paths:
            missing = sorted(actual_paths - set(expected_hashes))
            stale = sorted(set(expected_hashes) - actual_paths)
            if missing:
                errors.append("SHA256SUMS missing paths: " + ", ".join(missing))
            if stale:
                errors.append("SHA256SUMS has stale paths: " + ", ".join(stale))
        for relative in sorted(actual_paths & set(expected_hashes)):
            if digest(SYSTEM_SOURCE / relative) != expected_hashes[relative]:
                errors.append(f"asset checksum changed: {relative}")
    except (OSError, ValueError) as exc:
        errors.append(f"invalid SHA256SUMS: {exc}")

    return errors


def materialize(target: Path, profile: str, dry_run: bool, force: bool) -> int:
    errors = validate_source()
    if errors:
        raise MaterializeError("source verification failed:\n- " + "\n- ".join(errors))

    target = target.resolve(strict=False)
    plan = copy_plan(target, profile)
    conflicts: list[Path] = []
    pending: list[tuple[Path, Path]] = []

    for source, destination in plan:
        ensure_within(destination, target, "destination")
        if destination.exists():
            if not destination.is_file() or digest(destination) != digest(source):
                conflicts.append(destination)
        else:
            pending.append((source, destination))

    if conflicts and not force:
        rendered = "\n".join(f"- {path}" for path in conflicts)
        raise MaterializeError(
            "refusing to overwrite differing files:\n"
            f"{rendered}\nRe-run with --force only after replacement is authorized."
        )

    writes = pending + [
        (source, destination)
        for source, destination in plan
        if destination in conflicts
    ]
    if dry_run:
        for _, destination in writes:
            print(f"would write {destination}")
        print(f"dry-run: {len(writes)} write(s), profile={profile}")
        return 0

    for source, destination in writes:
        destination.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{destination.name}.", dir=destination.parent
        )
        os.close(descriptor)
        temporary = Path(temporary_name)
        try:
            shutil.copy2(source, temporary)
            os.replace(temporary, destination)
        finally:
            temporary.unlink(missing_ok=True)

    print(f"materialized {len(writes)} file(s), profile={profile}, target={target}")
    return verify(target, profile)


def verify(target: Path, profile: str) -> int:
    target = target.resolve(strict=False)
    mismatches: list[str] = []
    for source, destination in copy_plan(target, profile):
        ensure_within(destination, target, "destination")
        if not destination.is_file():
            mismatches.append(f"missing: {destination}")
        elif digest(destination) != digest(source):
            mismatches.append(f"changed: {destination}")
    if mismatches:
        raise MaterializeError("verification failed:\n- " + "\n- ".join(mismatches))
    print(f"verified {len(copy_plan(target, profile))} file(s), profile={profile}, target={target}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    write = commands.add_parser("materialize", help="copy the system into a target")
    write.add_argument("target", type=Path)
    write.add_argument("--profile", choices=PROFILES, default="tokens")
    write.add_argument("--dry-run", action="store_true")
    write.add_argument("--force", action="store_true")

    check = commands.add_parser("verify", help="verify a materialized target")
    check.add_argument("target", type=Path)
    check.add_argument("--profile", choices=PROFILES, default="tokens")

    commands.add_parser("verify-source", help="verify bundled source invariants")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "materialize":
            return materialize(args.target, args.profile, args.dry_run, args.force)
        if args.command == "verify":
            return verify(args.target, args.profile)
        errors = validate_source()
        if errors:
            raise MaterializeError("source verification failed:\n- " + "\n- ".join(errors))
        print(
            "source verified: DESIGN.md, tokens, font license, 31 exports, "
            "manifest targets, and local references"
        )
        return 0
    except MaterializeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
