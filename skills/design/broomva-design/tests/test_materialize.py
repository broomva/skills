from __future__ import annotations

import importlib.util
import io
import json
import shutil
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize.py"
SPEC = importlib.util.spec_from_file_location("broomva_materialize", SCRIPT)
assert SPEC and SPEC.loader
materialize = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(materialize)


class MaterializeTests(unittest.TestCase):
    def test_source_contract_is_valid_and_archive_inventory_is_stable(self) -> None:
        self.assertEqual(materialize.validate_source(), [])
        self.assertEqual(len(materialize.system_files()), 178)
        self.assertEqual(len(materialize.profile_entries("full")), 183)

    def test_foundation_is_product_neutral_and_self_contained(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "foundation", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((target / "DESIGN.md").is_file())
            self.assertTrue((root / "broomva-foundation.css").is_file())
            tokens = json.loads((root / "tokens.json").read_text())
            self.assertEqual(tokens["format"], "broomva-semantic-tokens/1")
            self.assertEqual(tokens["color"]["brand"]["blue"]["$value"], "oklch(0.60 0.12 260)")
            self.assertTrue((root / "assets/broomva-blackhole-logo.png").is_file())
            self.assertTrue((root / "fonts/OFL.txt").is_file())
            self.assertTrue((root / "references/product-patterns.md").is_file())
            self.assertTrue((root / "references/platform-adaptation.md").is_file())
            self.assertFalse((root / "tokens").exists())
            self.assertFalse((root / "components").exists())
            self.assertFalse((root / "references/agentic-work.md").exists())
            self.assertNotIn("Undertow", (target / "DESIGN.md").read_text())
            self.assertEqual(materialize.verify(target, "foundation"), 0)

    def test_essentials_preserves_the_legacy_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "essentials", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((root / "broomva-essentials.css").is_file())
            self.assertTrue((root / "assets/broomva-blackhole-logo.png").is_file())
            self.assertFalse((root / "broomva-foundation.css").exists())
            self.assertFalse((root / "tokens.json").exists())

    def test_tokens_preserves_the_legacy_layout(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "tokens", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((root / "styles.css").is_file())
            self.assertTrue((root / "broomva-essentials.css").is_file())
            self.assertTrue((root / "tokens/colors.css").is_file())
            self.assertTrue((root / "tokens/motion.css").is_file())
            self.assertTrue((root / "manifest.json").is_file())
            self.assertTrue((root / "adherence.oxlintrc.json").is_file())
            self.assertFalse((root / "components").exists())

    def test_web_exposes_22_general_components_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "web", False, False), 0)
            root = target / "design-system/broomva"
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual(len(manifest["components"]), 22)
            self.assertTrue((root / "components/core/Button.prompt.md").is_file())
            self.assertTrue((root / "components/overlays/Dialog.jsx").is_file())
            self.assertTrue((root / "index.js").is_file())
            self.assertTrue((root / "adherence.oxlintrc.json").is_file())
            self.assertFalse((root / "components/core/Composer.jsx").exists())
            self.assertFalse((root / "components/core/DotComet.jsx").exists())
            self.assertFalse((root / "components/work").exists())
            self.assertFalse((root / "tokens/motion.css").exists())
            self.assertFalse((root / "apps").exists())
            adapter_text = "\n".join(
                path.read_text(encoding="utf-8")
                for path in (root / "components").rglob("*")
                if path.is_file() and path.suffix in {".jsx", ".ts", ".md"}
            ).lower()
            for extension_term in (
                "undertow",
                "running work",
                "work item",
                "mission",
                "agent",
                "chat",
                "receipt",
                "needs you",
                "maestro",
            ):
                self.assertNotIn(extension_term, adapter_text)
            self.assertNotIn(
                "running", (root / "components/core/Card.d.ts").read_text().lower()
            )
            self.assertEqual(materialize.css_variable_errors("web"), [])
            tabs = (root / "components/navigation/Tabs.jsx").read_text()
            dialog = (root / "components/overlays/Dialog.jsx").read_text()
            palette = (root / "components/navigation/CommandPalette.jsx").read_text()
            menu = (root / "components/overlays/Menu.jsx").read_text()
            switch_types = (root / "components/forms/Switch.d.ts").read_text()
            self.assertIn('event.key === "ArrowRight"', tabs)
            self.assertIn("tabIndex={selected ? 0 : -1}", tabs)
            self.assertIn("querySelectorAll(FOCUSABLE)", dialog)
            self.assertIn("previousFocus.current?.focus?.()", dialog)
            self.assertIn('role="combobox"', palette)
            self.assertIn('role="listbox"', palette)
            self.assertIn('event.key === "ArrowDown"', palette)
            self.assertIn('event.key === "Enter"', palette)
            self.assertIn('role="menu"', menu)
            self.assertIn('event.key === "Home"', menu)
            self.assertIn("items[next].focus()", menu)
            self.assertIn("onExternalKeyDown?.(event)", menu)
            self.assertIn("onMouseEnter?.(event)", menu)
            self.assertIn("React.ButtonHTMLAttributes<HTMLButtonElement>", switch_types)
            switch_source = (root / "components/forms/Switch.jsx").read_text()
            self.assertIn("onClick?.(event)", switch_source)

            field = (root / "components/forms/Field.jsx").read_text()
            field_types = (root / "components/forms/Field.d.ts").read_text()
            dialog_types = (root / "components/overlays/Dialog.d.ts").read_text()
            self.assertIn("React.cloneElement", field)
            self.assertIn("<label", field)
            self.assertIn('"aria-describedby"', field)
            self.assertIn('"aria-invalid"', field)
            self.assertIn("children: React.ReactElement", field_types)
            self.assertNotIn("labelFor", field_types)
            self.assertNotIn("labelFor", field)
            self.assertNotIn("SwitchAccessibleName", switch_types)
            self.assertIn("buttonRef.current?.labels?.length", switch_source)
            self.assertNotIn('ariaLabel || "Dialog"', dialog)
            self.assertIn("throw new TypeError", dialog)
            self.assertIn("title: DialogTitle", dialog_types)

    def test_agentic_work_is_an_explicit_extension(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(
                materialize.materialize(target, "agentic-work", False, False), 0
            )
            root = target / "design-system/broomva"
            manifest = json.loads((root / "manifest.json").read_text())
            self.assertEqual(len(manifest["components"]), 31)
            declared = [item["sourcePath"] for item in manifest["components"]]
            declared += manifest["globalCssPaths"]
            for font in manifest["fonts"]:
                declared += font["files"]
            self.assertTrue(all((root / path).is_file() for path in declared))
            self.assertNotIn("cards", manifest)
            self.assertNotIn("templates", manifest)
            self.assertTrue((root / "components/core/Composer.jsx").is_file())
            self.assertTrue((root / "components/core/DotComet.jsx").is_file())
            self.assertTrue((root / "components/work/Undertow.jsx").is_file())
            self.assertTrue((root / "tokens/motion.css").is_file())
            self.assertTrue((root / "references/agentic-work.md").is_file())
            self.assertFalse((root / "apps/maestro").exists())
            self.assertFalse((root / "templates").exists())
            self.assertIn(
                "React.cloneElement",
                (root / "components/forms/Field.jsx").read_text(),
            )

    def test_full_keeps_complete_evidence_and_all_guidance(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "full", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((root / "components/core/Button.prompt.md").is_file())
            self.assertTrue((root / "templates/app-shell/AppShell.dc.html").is_file())
            self.assertTrue((root / "apps/maestro/MaestroApp.jsx").is_file())
            self.assertTrue((root / "_ds_bundle.js").is_file())
            self.assertTrue((root / "index.js").is_file())
            self.assertTrue((root / "broomva-foundation.css").is_file())
            self.assertTrue((root / "tokens.json").is_file())
            self.assertTrue((root / "references/agentic-work.md").is_file())
            self.assertEqual(materialize.verify(target, "full"), 0)

    def test_manifests_and_browser_references_resolve(self) -> None:
        self.assertEqual(materialize.local_reference_errors(), [])
        for profile in materialize.PROFILES:
            self.assertEqual(materialize.planned_css_reference_errors(profile), [])

    def test_portable_declarations_support_current_react_types(self) -> None:
        declarations = materialize.PORTABLE_SOURCE.glob("components/*/*.d.ts")
        for declaration in declarations:
            with self.subTest(declaration=declaration.name):
                text = declaration.read_text(encoding="utf-8")
                self.assertNotRegex(text, r"(?<!React\.)\bJSX\.Element\b")

    def test_product_profiles_prefer_accessible_portable_overrides(self) -> None:
        portable = materialize.PORTABLE_SOURCE.resolve()
        system = materialize.SYSTEM_SOURCE.resolve()
        for profile in ("web", "agentic-work"):
            entries = {
                destination.as_posix(): source.resolve()
                for source, destination in materialize.profile_entries(profile)
            }
            with self.subTest(profile=profile):
                self.assertEqual(entries["components/forms/Field.jsx"].parent.parent.parent, portable)
                self.assertEqual(entries["components/forms/Switch.jsx"].parent.parent.parent, portable)
                self.assertEqual(entries["components/overlays/Dialog.jsx"].parent.parent.parent, portable)
        full_entries = {
            destination.as_posix(): source.resolve()
            for source, destination in materialize.profile_entries("full")
        }
        self.assertEqual(
            full_entries["components/forms/Field.jsx"].parent.parent.parent,
            system,
        )

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(materialize.materialize(target, "web", True, False), 0)
            self.assertEqual(list(target.iterdir()), [])
            rendered = output.getvalue()
            self.assertIn("dry-run plan: profile=web", rendered)
            self.assertIn("components:", rendered)
            self.assertIn("references:", rendered)
            self.assertIn("use --verbose to list every path", rendered)
            self.assertNotIn("would write", rendered)

    def test_verbose_dry_run_lists_paths_after_grouped_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    materialize.materialize(
                        target, "foundation", True, False, verbose=True
                    ),
                    0,
                )
            rendered = output.getvalue()
            self.assertLess(rendered.index("writes:"), rendered.index("would write"))
            self.assertIn(f"would write {target.resolve() / 'DESIGN.md'}", rendered)

    def test_profile_recommendation_uses_target_facts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "package.json").write_text(
                json.dumps({"dependencies": {"react": "latest"}}),
                encoding="utf-8",
            )
            recommendation = materialize.recommend_profile(target)
            self.assertEqual(recommendation["profile"], "web")
            self.assertIn("React", " ".join(recommendation["reasons"]))

            agentic = materialize.recommend_profile(target, agentic_work=True)
            self.assertEqual(agentic["profile"], "agentic-work")

            maintainer = materialize.recommend_profile(target, maintainer=True)
            self.assertEqual(maintainer["profile"], "full")

            native = materialize.recommend_profile(target, platform="native")
            self.assertEqual(native["profile"], "foundation")

    def test_profile_recommendation_retains_an_exact_install_without_explicit_intent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "web", False, False), 0)
            recommendation = materialize.recommend_profile(target)
            self.assertEqual(recommendation["profile"], "web")
            self.assertEqual(recommendation["facts"]["installedProfile"], "web")

            maintainer = materialize.recommend_profile(target, maintainer=True)
            self.assertEqual(maintainer["profile"], "full")
            agentic = materialize.recommend_profile(target, agentic_work=True)
            self.assertEqual(agentic["profile"], "agentic-work")

    def test_profile_recommendation_rejects_invalid_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "package.json").write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(materialize.MaterializeError, "cannot inspect"):
                materialize.recommend_profile(target)

    def test_profile_recommendation_rejects_non_utf8_package_json(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "package.json").write_bytes(b"\xff")
            with self.assertRaisesRegex(materialize.MaterializeError, "cannot inspect"):
                materialize.recommend_profile(target)

    def test_profile_recommendation_rejects_unknown_frameworks(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(materialize.MaterializeError, "unknown framework"):
                materialize.recommend_profile(Path(directory), framework="SwiftUI")

    def test_recommend_cli_and_historical_profile_values_remain_available(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = io.StringIO()
            with redirect_stdout(output):
                self.assertEqual(
                    materialize.main(["recommend", directory, "--platform", "web"]),
                    0,
                )
            self.assertIn("recommended profile: web", output.getvalue())
        for profile in materialize.PROFILES:
            args = materialize.parser().parse_args(
                ["materialize", ".", "--profile", profile, "--dry-run"]
            )
            self.assertEqual(args.profile, profile)

    def test_verbose_requires_dry_run(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            errors = io.StringIO()
            with redirect_stdout(io.StringIO()):
                with mock.patch("sys.stderr", errors):
                    self.assertEqual(
                        materialize.main(["materialize", directory, "--verbose"]),
                        2,
                    )
            self.assertIn("--verbose requires --dry-run", errors.getvalue())

    def test_help_prioritizes_product_profiles_and_names_the_default(self) -> None:
        help_text = materialize.parser().format_help()
        materialize_help = materialize.parser()._subparsers._group_actions[0].choices[
            "materialize"
        ].format_help()
        self.assertIn("recommend", help_text)
        self.assertIn("Primary profiles", materialize_help)
        self.assertIn("default: foundation", materialize_help)
        self.assertIn("Advanced and compatibility", materialize_help)

    def test_refuses_differing_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "DESIGN.md").write_text("incumbent\n", encoding="utf-8")
            with self.assertRaises(materialize.MaterializeError):
                materialize.materialize(target, "foundation", False, False)
            self.assertEqual((target / "DESIGN.md").read_text(), "incumbent\n")

    def test_force_replaces_only_planned_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "DESIGN.md").write_text("incumbent\n", encoding="utf-8")
            untouched = target / "user-file.txt"
            untouched.write_text("keep me\n", encoding="utf-8")
            self.assertEqual(
                materialize.materialize(target, "foundation", False, True), 0
            )
            self.assertIn("# Design System: Broomva", (target / "DESIGN.md").read_text())
            self.assertEqual(untouched.read_text(), "keep me\n")

    def test_every_profile_is_idempotent(self) -> None:
        for profile in materialize.PROFILES:
            with self.subTest(profile=profile), tempfile.TemporaryDirectory() as directory:
                target = Path(directory)
                self.assertEqual(materialize.materialize(target, profile, False, False), 0)
                self.assertEqual(materialize.materialize(target, profile, False, False), 0)

    def test_profile_downgrade_requires_and_honors_explicit_prune(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "full", False, False), 0)
            with self.assertRaises(materialize.MaterializeError):
                materialize.verify(target, "web")
            with self.assertRaises(materialize.MaterializeError):
                materialize.materialize(target, "web", False, True)
            self.assertEqual(
                materialize.materialize(target, "web", False, False, prune=True), 0
            )
            root = target / "design-system/broomva"
            self.assertFalse((root / "components/work").exists())
            self.assertFalse((root / "tokens/motion.css").exists())
            self.assertFalse((root / "apps/maestro").exists())
            self.assertFalse((root / "templates").exists())
            self.assertEqual(materialize.verify(target, "web"), 0)

    def test_prune_rejects_managed_paths_through_symlinked_parent(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            target = Path(directory)
            external = Path(outside) / "components"
            undertow = external / "work/Undertow.jsx"
            undertow.parent.mkdir(parents=True)
            undertow.write_text("external\n", encoding="utf-8")
            root = target / "design-system/broomva"
            root.mkdir(parents=True)
            (root / "components").symlink_to(external, target_is_directory=True)

            with self.assertRaisesRegex(materialize.MaterializeError, "escapes target root"):
                materialize.materialize(
                    target, "foundation", False, True, prune=True
                )
            self.assertEqual(undertow.read_text(encoding="utf-8"), "external\n")

    def test_prune_rechecks_parent_after_extra_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory, tempfile.TemporaryDirectory() as outside:
            target = Path(directory)
            root = target / "design-system/broomva"
            internal = root / "components/work/Undertow.jsx"
            internal.parent.mkdir(parents=True)
            internal.write_text("managed\n", encoding="utf-8")
            external = Path(outside) / "components"
            external_undertow = external / "work/Undertow.jsx"
            external_undertow.parent.mkdir(parents=True)
            external_undertow.write_text("external\n", encoding="utf-8")
            original_extra_owned_files = materialize.extra_owned_files

            def discover_then_swap(discovery_target: Path, profile: str) -> list[Path]:
                extras = original_extra_owned_files(discovery_target, profile)
                components = root / "components"
                shutil.move(components, root / "components-before-swap")
                components.symlink_to(external, target_is_directory=True)
                return extras

            with mock.patch.object(
                materialize, "extra_owned_files", side_effect=discover_then_swap
            ):
                with self.assertRaisesRegex(materialize.MaterializeError, "unsafe parent"):
                    materialize.materialize(
                        target, "foundation", False, True, prune=True
                    )
            self.assertEqual(
                external_undertow.read_text(encoding="utf-8"), "external\n"
            )

    def test_prune_preserves_leaf_replaced_after_quarantine_digest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "full", False, False), 0)
            replacement = target / "design-system/broomva/components/work/Undertow.jsx"
            original_digest = materialize.digest_managed_file
            replaced = False

            def digest_then_replace(path: Path, root: Path) -> str:
                nonlocal replaced
                value = original_digest(path, root)
                if not replaced and path.name.startswith(".Undertow.jsx.broomva-prune-"):
                    replacement.write_text("replacement\n", encoding="utf-8")
                    replaced = True
                return value

            with mock.patch.object(
                materialize, "digest_managed_file", side_effect=digest_then_replace
            ):
                with self.assertRaisesRegex(
                    materialize.MaterializeError, "unexpected managed file"
                ):
                    materialize.materialize(
                        target, "web", False, False, prune=True
                    )
            self.assertEqual(replacement.read_text(encoding="utf-8"), "replacement\n")

    def test_prune_restores_quarantines_when_interrupted(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "full", False, False), 0)
            root = target / "design-system/broomva"
            undertow = root / "components/work/Undertow.jsx"
            original = undertow.read_bytes()
            original_digest = materialize.digest_managed_file

            def interrupt_quarantine_digest(path: Path, digest_root: Path) -> str:
                if ".broomva-prune-" in path.name:
                    raise KeyboardInterrupt
                return original_digest(path, digest_root)

            with mock.patch.object(
                materialize,
                "digest_managed_file",
                side_effect=interrupt_quarantine_digest,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    materialize.materialize(
                        target, "web", False, False, prune=True
                    )
            self.assertEqual(undertow.read_bytes(), original)
            self.assertEqual(list(root.rglob("*.broomva-prune-*")), [])


if __name__ == "__main__":
    unittest.main()
