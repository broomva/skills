from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


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

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "web", True, False), 0)
            self.assertEqual(list(target.iterdir()), [])

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


if __name__ == "__main__":
    unittest.main()
