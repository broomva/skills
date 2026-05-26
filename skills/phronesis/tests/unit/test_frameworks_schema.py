"""Property tests for the framework registry schema.

Every YAML at frameworks/<category>/<slug>.yaml must satisfy _schema.yaml.
This file tests the loader + validator. Per-framework smoke tests live in
tests/unit/test_framework_<slug>.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from core.frameworks import FRAMEWORKS_ROOT, load_all, load_framework

pytestmark = pytest.mark.unit


_VALID_FW = """
id: "test-fw"
name: "Test Framework"
source_firm: "Test"
source_year: 2026
source_citation: "Test (2026)"
category: "strategy"
purpose: "test purpose"
inputs: []
dimensions: ["d1"]
scoring_rubric:
  formula: null
  output_unit: "score"
  thresholds: null
output_shape:
  type: "Score"
  fields: {}
when_to_use:
  - "condition a"
  - "condition b"
  - "condition c"
when_NOT_to_use:
  - "anti-pattern a"
  - "anti-pattern b"
example_application: {}
relationships: {}
citations: []
"""


def _write(path: Path, content: str) -> Path:
    path.write_text(content)
    return path


class TestSchemaFile:
    def test_schema_yaml_exists(self):
        assert (FRAMEWORKS_ROOT / "_schema.yaml").exists()

    def test_schema_yaml_is_valid_yaml(self):
        schema = yaml.safe_load((FRAMEWORKS_ROOT / "_schema.yaml").read_text())
        assert schema["title"] == "Phronesis Framework"
        assert "id" in schema["required"]
        assert "category" in schema["required"]


class TestLoadFramework:
    def test_load_accepts_valid_framework(self, tmp_path: Path):
        path = _write(tmp_path / "good.yaml", _VALID_FW)
        fw = load_framework(path)
        assert fw.id == "test-fw"
        assert fw.category == "strategy"
        assert fw.is_d_scope is False

    def test_load_rejects_uppercase_id(self, tmp_path: Path):
        bad = _VALID_FW.replace('id: "test-fw"', 'id: "BadID"')
        path = _write(tmp_path / "bad.yaml", bad)
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            load_framework(path)

    def test_load_rejects_unknown_category(self, tmp_path: Path):
        bad = _VALID_FW.replace('category: "strategy"', 'category: "unknown"')
        path = _write(tmp_path / "bad.yaml", bad)
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            load_framework(path)

    def test_load_rejects_too_few_when_to_use(self, tmp_path: Path):
        bad = _VALID_FW.replace(
            'when_to_use:\n  - "condition a"\n  - "condition b"\n  - "condition c"',
            'when_to_use:\n  - "only one"',
        )
        path = _write(tmp_path / "bad.yaml", bad)
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            load_framework(path)

    def test_load_rejects_too_few_when_not_to_use(self, tmp_path: Path):
        bad = _VALID_FW.replace(
            'when_NOT_to_use:\n  - "anti-pattern a"\n  - "anti-pattern b"',
            'when_NOT_to_use:\n  - "only one"',
        )
        path = _write(tmp_path / "bad.yaml", bad)
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            load_framework(path)

    def test_load_rejects_unknown_output_shape_type(self, tmp_path: Path):
        bad = _VALID_FW.replace('type: "Score"', 'type: "UnknownType"')
        path = _write(tmp_path / "bad.yaml", bad)
        import jsonschema

        with pytest.raises(jsonschema.ValidationError):
            load_framework(path)

    def test_load_accepts_d_scope_marker(self, tmp_path: Path):
        d_scope = _VALID_FW + "\nis_d_scope: true\n"
        path = _write(tmp_path / "stub.yaml", d_scope)
        fw = load_framework(path)
        assert fw.is_d_scope is True


class TestLoadAll:
    def test_load_all_skips_schema_yaml(self):
        # Even with no framework YAMLs present, load_all() ignores _schema.yaml.
        result = load_all()
        # Phase B.0 hasn't shipped any frameworks yet — registry is empty.
        # B.1 ships RICE; after that the assert becomes "rice in result".
        assert "_schema" not in result

    def test_load_all_returns_dict(self):
        assert isinstance(load_all(), dict)
