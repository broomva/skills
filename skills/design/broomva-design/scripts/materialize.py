#!/usr/bin/env python3
"""Safely materialize and verify the layered Broomva design system."""

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
PORTABLE_SOURCE = SKILL_DIR / "assets" / "portable"
REFERENCE_SOURCE = SKILL_DIR / "references"
SYSTEM_DEST = Path("design-system") / "broomva"
PROFILES = ("essentials", "tokens", "foundation", "web", "agentic-work", "full")

FOUNDATION_SYSTEM_FILES = {
    "assets/broomva-blackhole-logo.png",
    "fonts/CalSans-SemiBold.ttf",
    "fonts/OFL.txt",
}
FOUNDATION_PORTABLE_FILES = {"broomva-foundation.css", "tokens.json"}
LEGACY_ESSENTIALS = {
    "broomva-essentials.css",
    "assets/broomva-blackhole-logo.png",
}
LEGACY_TOKEN_FILES = LEGACY_ESSENTIALS | {
    "styles.css",
    "manifest.json",
    "adherence.oxlintrc.json",
}
LEGACY_TOKEN_PREFIXES = ("tokens/", "fonts/")
AGENTIC_TOKEN_FILES = {
    "tokens/colors.css",
    "tokens/typography.css",
    "tokens/spacing.css",
    "tokens/glass.css",
    "tokens/base.css",
    "tokens/motion.css",
}
GENERAL_CORE = {"Avatar", "Button", "Card", "IconButton", "Input", "StatusBadge"}
GENERAL_COMPONENT_PREFIXES = (
    "components/forms/",
    "components/navigation/",
    "components/overlays/",
)
COMPONENT_SUFFIXES = (".jsx", ".d.ts", ".prompt.md")
PORTABLE_WEB_FILES = {
    "styles.css",
    "index.js",
    "index.d.ts",
    "manifest.json",
    "adherence.oxlintrc.json",
}
GENERAL_REFERENCES = ("product-patterns.md", "platform-adaptation.md")
AGENTIC_REFERENCE = "agentic-work.md"


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


class MaterializeError(RuntimeError):
    """An expected, user-actionable materialization error."""


def local_path(source: Path, reference: str) -> Path | None:
    parsed = urlsplit(reference.strip())
    if parsed.scheme or parsed.netloc or not parsed.path or parsed.path.startswith("/"):
        return None
    return (source.parent / parsed.path).resolve(strict=False)


def local_reference_errors() -> list[str]:
    """Validate the complete archived evidence tree."""

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


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def system_files() -> list[Path]:
    return sorted(path for path in SYSTEM_SOURCE.rglob("*") if path.is_file())


def is_general_component(relative: str) -> bool:
    if not relative.endswith(COMPONENT_SUFFIXES):
        return False
    if relative.startswith(GENERAL_COMPONENT_PREFIXES):
        return True
    if not relative.startswith("components/core/"):
        return False
    filename = relative.removeprefix("components/core/")
    return any(filename.startswith(f"{name}.") for name in GENERAL_CORE)


def is_any_component(relative: str) -> bool:
    return relative.startswith("components/") and relative.endswith(COMPONENT_SUFFIXES)


def add_entry(
    entries: dict[str, Path], source: Path, destination: str
) -> None:
    incumbent = entries.get(destination)
    if incumbent is not None and incumbent != source:
        raise MaterializeError(
            f"profile maps two sources to {destination}: {incumbent} and {source}"
        )
    entries[destination] = source


def add_references(entries: dict[str, Path], names: tuple[str, ...]) -> None:
    for name in names:
        add_entry(entries, REFERENCE_SOURCE / name, f"references/{name}")


def profile_entries(profile: str) -> list[tuple[Path, Path]]:
    """Return source files and destinations relative to design-system/broomva."""

    if profile not in PROFILES:
        raise MaterializeError(f"unknown profile: {profile}")

    entries: dict[str, Path] = {}
    system_by_relative = {
        path.relative_to(SYSTEM_SOURCE).as_posix(): path for path in system_files()
    }

    if profile == "full":
        for relative, source in system_by_relative.items():
            add_entry(entries, source, relative)
        for relative in FOUNDATION_PORTABLE_FILES:
            add_entry(entries, PORTABLE_SOURCE / relative, relative)
        add_references(entries, GENERAL_REFERENCES + (AGENTIC_REFERENCE,))
        return [(source, Path(destination)) for destination, source in sorted(entries.items())]

    if profile == "essentials":
        for relative in LEGACY_ESSENTIALS:
            add_entry(entries, system_by_relative[relative], relative)
        return [(source, Path(destination)) for destination, source in sorted(entries.items())]

    if profile == "tokens":
        for relative, source in system_by_relative.items():
            if relative in LEGACY_TOKEN_FILES or relative.startswith(
                LEGACY_TOKEN_PREFIXES
            ):
                add_entry(entries, source, relative)
        return [(source, Path(destination)) for destination, source in sorted(entries.items())]

    for relative in FOUNDATION_PORTABLE_FILES:
        add_entry(entries, PORTABLE_SOURCE / relative, relative)
    for relative in FOUNDATION_SYSTEM_FILES:
        add_entry(entries, system_by_relative[relative], relative)
    add_references(entries, GENERAL_REFERENCES)

    if profile == "foundation":
        return [(source, Path(destination)) for destination, source in sorted(entries.items())]

    add_entry(entries, PORTABLE_SOURCE / "styles.css", "styles.css")

    if profile == "web":
        for relative in PORTABLE_WEB_FILES:
            add_entry(entries, PORTABLE_SOURCE / relative, relative)
        for relative, source in system_by_relative.items():
            if is_general_component(relative):
                portable_override = PORTABLE_SOURCE / relative
                add_entry(
                    entries,
                    portable_override if portable_override.is_file() else source,
                    relative,
                )
        return [(source, Path(destination)) for destination, source in sorted(entries.items())]

    # agentic-work: use the full public entry points and motion-enabled stylesheet,
    # but exclude specimens, templates, desktop kits, and the Maestro reference app.
    entries.pop("styles.css")
    for relative in {
        "styles.css",
        "adherence.oxlintrc.json",
        "index.js",
        "index.d.ts",
    }:
        add_entry(entries, system_by_relative[relative], relative)
    for relative in AGENTIC_TOKEN_FILES:
        add_entry(entries, system_by_relative[relative], relative)
    add_entry(
        entries,
        PORTABLE_SOURCE / "manifest.agentic-work.json",
        "manifest.json",
    )
    for relative, source in system_by_relative.items():
        if is_any_component(relative):
            add_entry(entries, source, relative)
    add_references(entries, (AGENTIC_REFERENCE,))
    return [(source, Path(destination)) for destination, source in sorted(entries.items())]


def source_files(profile: str) -> list[Path]:
    """Compatibility helper returning the sources used by a profile."""

    return [source for source, _ in profile_entries(profile)]


def copy_plan(target: Path, profile: str) -> list[tuple[Path, Path]]:
    plan = [(DESIGN_SOURCE, target / "DESIGN.md")]
    plan.extend(
        (source, target / SYSTEM_DEST / destination)
        for source, destination in profile_entries(profile)
    )
    return plan


def ensure_within(path: Path, root: Path, label: str) -> None:
    resolved = path.resolve(strict=False)
    resolved_root = root.resolve(strict=False)
    if resolved != resolved_root and resolved_root not in resolved.parents:
        raise MaterializeError(f"{label} escapes target root: {path}")


def exported_names(index: str) -> set[str]:
    names: set[str] = set()
    for clause in re.findall(r"export\s*\{([^}]+)\}", index):
        for item in clause.split(","):
            names.add(item.strip().split(" as ")[-1])
    return names


def manifest_errors(
    manifest_path: Path,
    index_path: Path,
    expected_count: int,
    expected_namespace: str,
    available: set[str],
) -> list[str]:
    errors: list[str] = []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        exports = manifest.get("components", [])
        if len(exports) != expected_count:
            errors.append(
                f"{manifest_path.name} declares {len(exports)} components, expected {expected_count}"
            )
        if manifest.get("namespace") != expected_namespace:
            errors.append(f"{manifest_path.name} namespace changed")
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
            if relative not in available:
                errors.append(f"{manifest_path.name} target missing: {relative}")

        public_names = exported_names(index_path.read_text(encoding="utf-8"))
        expected_names = {item["name"] for item in exports}
        missing_exports = sorted(expected_names - public_names)
        extra_exports = sorted(public_names - expected_names)
        if missing_exports:
            errors.append(f"{index_path.name} missing exports: " + ", ".join(missing_exports))
        if extra_exports:
            errors.append(f"{index_path.name} has undeclared exports: " + ", ".join(extra_exports))
    except (OSError, json.JSONDecodeError, KeyError) as exc:
        errors.append(f"invalid {manifest_path.name}: {exc}")
    return errors


def checksum_errors(root: Path) -> list[str]:
    errors: list[str] = []
    checksum_path = root / "SHA256SUMS"
    try:
        expected_hashes: dict[str, str] = {}
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            checksum, relative = line.split(maxsplit=1)
            expected_hashes[relative.removeprefix("./")] = checksum
        actual_paths = {
            path.relative_to(root).as_posix()
            for path in root.rglob("*")
            if path.is_file() and path != checksum_path
        }
        if set(expected_hashes) != actual_paths:
            missing = sorted(actual_paths - set(expected_hashes))
            stale = sorted(set(expected_hashes) - actual_paths)
            if missing:
                errors.append(f"{root.name}/SHA256SUMS missing paths: " + ", ".join(missing))
            if stale:
                errors.append(f"{root.name}/SHA256SUMS has stale paths: " + ", ".join(stale))
        for relative in sorted(actual_paths & set(expected_hashes)):
            if digest(root / relative) != expected_hashes[relative]:
                errors.append(f"{root.name} asset checksum changed: {relative}")
    except (OSError, ValueError) as exc:
        errors.append(f"invalid {root.name}/SHA256SUMS: {exc}")
    return errors


def planned_css_reference_errors(profile: str) -> list[str]:
    errors: list[str] = []
    entries = profile_entries(profile)
    available = {destination.as_posix() for _, destination in entries}
    css_reference = re.compile(r"(?:@import\s+)?url\(\s*(['\"]?)([^)'\"]+)\1\s*\)")
    for source, destination in entries:
        if source.suffix != ".css":
            continue
        for _, reference in css_reference.findall(source.read_text(encoding="utf-8")):
            parsed = urlsplit(reference.strip())
            if parsed.scheme or parsed.netloc or parsed.path.startswith("/"):
                continue
            target = os.path.normpath(destination.parent / parsed.path)
            if target not in available:
                errors.append(f"{profile} profile CSS target missing: {destination} -> {reference}")
    return errors


def css_variable_errors(profile: str) -> list[str]:
    """Require every CSS custom property consumed by a profile to be defined."""

    used: set[str] = set()
    defined: set[str] = set()
    for source, _ in profile_entries(profile):
        if source.suffix.lower() not in {".css", ".js", ".jsx", ".ts"}:
            continue
        text = source.read_text(encoding="utf-8", errors="replace")
        used.update(re.findall(r"var\((--[A-Za-z0-9-]+)", text))
        if source.suffix.lower() == ".css":
            defined.update(re.findall(r"(?m)^\s*(--[A-Za-z0-9-]+)\s*:", text))
    return [f"{profile} profile CSS variable undefined: {name}" for name in sorted(used - defined)]


def validate_source() -> list[str]:
    errors: list[str] = []
    if not DESIGN_SOURCE.is_file():
        errors.append("missing DESIGN.md")
    else:
        design = DESIGN_SOURCE.read_text(encoding="utf-8")
        for section in range(1, 7):
            if f"## {section}." not in design:
                errors.append(f"DESIGN.md missing section {section}")
        for phrase in (
            "Blue-black ink",
            "product-neutral",
            "Domain independence",
            "prefers-reduced-motion",
        ):
            if phrase not in design:
                errors.append(f"DESIGN.md missing canonical phrase: {phrase}")

    agentic = REFERENCE_SOURCE / AGENTIC_REFERENCE
    if not agentic.is_file():
        errors.append(f"missing reference: {AGENTIC_REFERENCE}")
    else:
        text = agentic.read_text(encoding="utf-8")
        for phrase in ("Undertow", "Needs you", "Extension boundary"):
            if phrase not in text:
                errors.append(f"{AGENTIC_REFERENCE} missing extension phrase: {phrase}")

    required = {
        SYSTEM_SOURCE / "_ds_bundle.js": "BroomvaDesignSystem_5727d9",
        SYSTEM_SOURCE / "index.js": "export { Button }",
        SYSTEM_SOURCE / "readme.md": "Broomva Design System",
        SYSTEM_SOURCE / "broomva-look-spec.md": "Broomva look",
        SYSTEM_SOURCE / "tokens/colors.css": "--bv-ink:",
        SYSTEM_SOURCE / "tokens/typography.css": "--bv-font-sans:",
        SYSTEM_SOURCE / "tokens/spacing.css": "--bv-space-1:",
        SYSTEM_SOURCE / "tokens/glass.css": "Glass is EARNED",
        SYSTEM_SOURCE / "tokens/motion.css": "prefers-reduced-motion",
        SYSTEM_SOURCE / "fonts/OFL.txt": "SIL OPEN FONT LICENSE Version 1.1",
        PORTABLE_SOURCE / "broomva-foundation.css": "Broomva platform-neutral web foundation",
        PORTABLE_SOURCE / "tokens.json": "broomva-semantic-tokens/1",
        PORTABLE_SOURCE / "styles.css": "Broomva product-neutral web entrypoint",
        PORTABLE_SOURCE / "index.js": "export { Button }",
        PORTABLE_SOURCE / "components/navigation/Tabs.jsx": "ArrowRight",
        PORTABLE_SOURCE / "components/navigation/CommandPalette.jsx": 'role="combobox"',
        PORTABLE_SOURCE / "components/overlays/Dialog.jsx": "previousFocus",
        PORTABLE_SOURCE / "components/overlays/Menu.jsx": 'event.key === "Home"',
        PORTABLE_SOURCE / "components/forms/Switch.d.ts": "ButtonHTMLAttributes",
    }
    for path, anchor in required.items():
        if not path.is_file():
            errors.append(f"missing asset: {path.relative_to(SKILL_DIR)}")
            continue
        if anchor not in path.read_text(encoding="utf-8", errors="replace"):
            errors.append(f"asset {path.relative_to(SKILL_DIR)} missing anchor: {anchor}")

    system_available = {
        path.relative_to(SYSTEM_SOURCE).as_posix() for path in system_files()
    }
    errors.extend(
        manifest_errors(
            SYSTEM_SOURCE / "manifest.json",
            SYSTEM_SOURCE / "index.js",
            31,
            "BroomvaDesignSystem_5727d9",
            system_available,
        )
    )
    agentic_available = {
        destination.as_posix() for _, destination in profile_entries("agentic-work")
    }
    errors.extend(
        manifest_errors(
            PORTABLE_SOURCE / "manifest.agentic-work.json",
            SYSTEM_SOURCE / "index.js",
            31,
            "BroomvaDesignSystem_5727d9_agentic_work",
            agentic_available,
        )
    )

    forbidden_web_phrases = (
        "undertow",
        "composer",
        "running work",
        "work item",
        "needs you",
        "maestro",
        "claude continues",
        "run/7c2f",
        "gate every run",
        "before the loop",
        "run flags",
        'placeholder="prompt"',
    )
    for source, destination in profile_entries("web"):
        if destination.parts[0] == "references" or source.suffix.lower() not in {
            ".css",
            ".js",
            ".jsx",
            ".ts",
            ".md",
            ".json",
        }:
            continue
        text = source.read_text(encoding="utf-8", errors="replace").lower()
        for phrase in forbidden_web_phrases:
            if phrase in text:
                errors.append(f"web profile leaks agentic phrase in {destination}: {phrase}")
    web_available = {destination.as_posix() for _, destination in profile_entries("web")}
    errors.extend(
        manifest_errors(
            PORTABLE_SOURCE / "manifest.json",
            PORTABLE_SOURCE / "index.js",
            22,
            "BroomvaDesignSystem_5727d9_foundation",
            web_available,
        )
    )

    errors.extend(local_reference_errors())
    for profile in PROFILES:
        errors.extend(planned_css_reference_errors(profile))
    errors.extend(css_variable_errors("web"))
    errors.extend(checksum_errors(SYSTEM_SOURCE))
    errors.extend(checksum_errors(PORTABLE_SOURCE))
    return errors


def managed_destinations() -> set[str]:
    return {
        destination.as_posix()
        for profile in PROFILES
        for _, destination in profile_entries(profile)
    }


def extra_owned_files(target: Path, profile: str) -> list[Path]:
    expected = {destination.as_posix() for _, destination in profile_entries(profile)}
    root = target / SYSTEM_DEST
    return [
        root / relative
        for relative in sorted(managed_destinations() - expected)
        if (root / relative).is_file() or (root / relative).is_symlink()
    ]


def owned_source_digests(destination: Path) -> set[str]:
    relative = destination.as_posix()
    return {
        digest(source)
        for profile in PROFILES
        for source, candidate in profile_entries(profile)
        if candidate.as_posix() == relative
    }


def materialize(
    target: Path,
    profile: str,
    dry_run: bool,
    force: bool,
    prune: bool = False,
) -> int:
    errors = validate_source()
    if errors:
        raise MaterializeError("source verification failed:\n- " + "\n- ".join(errors))

    target = target.resolve(strict=False)
    plan = copy_plan(target, profile)
    extras = extra_owned_files(target, profile)
    if extras and not prune:
        rendered = "\n".join(f"- {path}" for path in extras)
        raise MaterializeError(
            "target contains files owned by another Broomva profile:\n"
            f"{rendered}\nRe-run with --prune to authorize their removal."
        )
    modified_extras = [
        path
        for path in extras
        if path.is_symlink()
        or digest(path)
        not in owned_source_digests(path.relative_to(target / SYSTEM_DEST))
    ]
    if modified_extras and not force:
        rendered = "\n".join(f"- {path}" for path in modified_extras)
        raise MaterializeError(
            "refusing to prune modified managed files:\n"
            f"{rendered}\nRe-run with both --prune and --force only after deletion is authorized."
        )
    conflicts: list[Path] = []
    pending: list[tuple[Path, Path]] = []
    managed_replacements: list[tuple[Path, Path]] = []

    for source, destination in plan:
        ensure_within(destination, target, "destination")
        if destination.exists():
            if not destination.is_file() or digest(destination) != digest(source):
                try:
                    relative = destination.relative_to(target / SYSTEM_DEST)
                except ValueError:
                    relative = None
                if (
                    prune
                    and relative is not None
                    and not destination.is_symlink()
                    and destination.is_file()
                    and digest(destination) in owned_source_digests(relative)
                ):
                    managed_replacements.append((source, destination))
                else:
                    conflicts.append(destination)
        else:
            pending.append((source, destination))

    if conflicts and not force:
        rendered = "\n".join(f"- {path}" for path in conflicts)
        raise MaterializeError(
            "refusing to overwrite differing files:\n"
            f"{rendered}\nRe-run with --force only after replacement is authorized."
        )

    writes = pending + managed_replacements + [
        (source, destination)
        for source, destination in plan
        if destination in conflicts
    ]
    if dry_run:
        for _, destination in writes:
            print(f"would write {destination}")
        for path in extras:
            print(f"would remove {path}")
        print(
            f"dry-run: {len(writes)} write(s), {len(extras)} removal(s), "
            f"profile={profile}"
        )
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

    for path in extras:
        path.unlink()
    root = target / SYSTEM_DEST
    if root.is_dir():
        for directory in sorted(
            (path for path in root.rglob("*") if path.is_dir()),
            key=lambda path: len(path.parts),
            reverse=True,
        ):
            try:
                directory.rmdir()
            except OSError:
                pass

    print(
        f"materialized {len(writes)} file(s), pruned {len(extras)} file(s), "
        f"profile={profile}, target={target}"
    )
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
    mismatches.extend(
        f"unexpected managed file: {path}" for path in extra_owned_files(target, profile)
    )
    if mismatches:
        raise MaterializeError("verification failed:\n- " + "\n- ".join(mismatches))
    print(f"verified {len(copy_plan(target, profile))} file(s), profile={profile}, target={target}")
    return 0


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description=__doc__)
    commands = root.add_subparsers(dest="command", required=True)

    write = commands.add_parser("materialize", help="copy the system into a target")
    write.add_argument("target", type=Path)
    write.add_argument("--profile", choices=PROFILES, default="foundation")
    write.add_argument("--dry-run", action="store_true")
    write.add_argument("--force", action="store_true")
    write.add_argument(
        "--prune",
        action="store_true",
        help="remove files owned by a previously materialized broader profile",
    )

    check = commands.add_parser("verify", help="verify a materialized target")
    check.add_argument("target", type=Path)
    check.add_argument("--profile", choices=PROFILES, default="foundation")

    commands.add_parser("verify-source", help="verify bundled source invariants")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "materialize":
            return materialize(
                args.target, args.profile, args.dry_run, args.force, args.prune
            )
        if args.command == "verify":
            return verify(args.target, args.profile)
        errors = validate_source()
        if errors:
            raise MaterializeError("source verification failed:\n- " + "\n- ".join(errors))
        print(
            "source verified: neutral DESIGN.md, portable foundation, 22 general web "
            "exports, 31 agentic/full exports, manifests, checksums, and local references"
        )
        return 0
    except MaterializeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
