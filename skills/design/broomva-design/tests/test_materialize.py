from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "materialize.py"
SPEC = importlib.util.spec_from_file_location("broomva_materialize", SCRIPT)
assert SPEC and SPEC.loader
materialize = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(materialize)


class MaterializeTests(unittest.TestCase):
    def test_source_contract_is_valid(self) -> None:
        self.assertEqual(materialize.validate_source(), [])
        self.assertEqual(len(materialize.source_files("full")), 178)

    def test_essentials_profile_is_minimal_and_verifiable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "essentials", False, False), 0)
            self.assertTrue((target / "DESIGN.md").is_file())
            self.assertTrue(
                (target / "design-system/broomva/broomva-essentials.css").is_file()
            )
            self.assertTrue(
                (target / "design-system/broomva/assets/broomva-blackhole-logo.png").is_file()
            )
            self.assertFalse((target / "design-system/broomva/components").exists())
            self.assertEqual(materialize.verify(target, "essentials"), 0)

    def test_tokens_profile_includes_contract_and_license(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "tokens", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((root / "tokens/colors.css").is_file())
            self.assertTrue((root / "fonts/CalSans-SemiBold.ttf").is_file())
            self.assertTrue((root / "fonts/OFL.txt").is_file())
            self.assertTrue((root / "adherence.oxlintrc.json").is_file())
            self.assertFalse((root / "components").exists())

    def test_full_profile_includes_components_templates_and_reference_app(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "full", False, False), 0)
            root = target / "design-system/broomva"
            self.assertTrue((root / "components/core/Button.prompt.md").is_file())
            self.assertTrue((root / "templates/app-shell/AppShell.dc.html").is_file())
            self.assertTrue((root / "apps/maestro/MaestroApp.jsx").is_file())
            self.assertTrue((root / "_ds_bundle.js").is_file())
            self.assertTrue((root / "index.js").is_file())
            self.assertEqual(materialize.verify(target, "full"), 0)

    def test_manifest_and_browser_references_resolve(self) -> None:
        self.assertEqual(materialize.local_reference_errors(), [])

    def test_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "tokens", True, False), 0)
            self.assertEqual(list(target.iterdir()), [])

    def test_refuses_differing_file_without_force(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "DESIGN.md").write_text("incumbent\n", encoding="utf-8")
            with self.assertRaises(materialize.MaterializeError):
                materialize.materialize(target, "essentials", False, False)
            self.assertEqual((target / "DESIGN.md").read_text(), "incumbent\n")

    def test_force_replaces_only_planned_files(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            (target / "DESIGN.md").write_text("incumbent\n", encoding="utf-8")
            untouched = target / "user-file.txt"
            untouched.write_text("keep me\n", encoding="utf-8")
            self.assertEqual(materialize.materialize(target, "essentials", False, True), 0)
            self.assertIn("# Design System: Broomva", (target / "DESIGN.md").read_text())
            self.assertEqual(untouched.read_text(), "keep me\n")

    def test_materialization_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            self.assertEqual(materialize.materialize(target, "tokens", False, False), 0)
            self.assertEqual(materialize.materialize(target, "tokens", False, False), 0)


if __name__ == "__main__":
    unittest.main()
