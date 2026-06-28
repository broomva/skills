"""Framework registry — loads all YAMLs at frameworks/ and validates them
against frameworks/_schema.yaml.

Phase 1 ships 14 implemented frameworks + 13 D-scope stubs.
Phase 3 mirrors this in life-phronesis Rust crate.

P7 enforcement: framework_selector caps active frameworks at ≤5 per
engagement. The registry just loads + validates; selection happens in
core/selector.py.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

FRAMEWORKS_ROOT = Path(__file__).resolve().parent.parent / "frameworks"


class FrameworkInput(BaseModel):
    """One input parameter a framework consumes."""

    name: str
    type: str
    description: str


class Framework(BaseModel):
    """In-memory representation of a framework YAML.

    Mirrors frameworks/_schema.yaml. Pydantic does the runtime validation;
    the YAML schema gets validated separately via jsonschema in
    `load_framework` so we get JSON-Schema-quality error messages.

    The YAML field `when_NOT_to_use` (mixed case per design spec Appendix A)
    is exposed as `when_not_to_use` in Python via Pydantic alias. Both names
    work on construction — population_by_field_name is enabled.
    """

    model_config = {"populate_by_name": True}

    id: str
    name: str
    source_firm: str
    source_year: int
    source_citation: str
    category: str
    purpose: str
    inputs: list[FrameworkInput] = Field(default_factory=list)
    dimensions: list[str] = Field(default_factory=list)
    scoring_rubric: dict[str, Any]
    output_shape: dict[str, Any]
    when_to_use: list[str]
    when_not_to_use: list[str] = Field(alias="when_NOT_to_use")
    example_application: dict[str, Any] = Field(default_factory=dict)
    relationships: dict[str, list[str]] = Field(default_factory=dict)
    citations: list[str] = Field(default_factory=list)
    is_d_scope: bool = False


def _validate_against_schema(raw: dict[str, Any]) -> None:
    """Validate a YAML dict against frameworks/_schema.yaml using jsonschema.

    Raises jsonschema.ValidationError on first violation. We keep this
    optional — if jsonschema isn't installed the Pydantic layer still
    catches missing/wrong-typed fields.
    """
    schema_path = FRAMEWORKS_ROOT / "_schema.yaml"
    if not schema_path.exists():
        return
    try:
        import jsonschema
    except ImportError:
        return
    schema = yaml.safe_load(schema_path.read_text())
    jsonschema.validate(raw, schema)


def load_framework(path: Path) -> Framework:
    """Load and validate one framework YAML.

    Validates against `_schema.yaml` first (JSON Schema), then through
    Pydantic. Two layers because they catch different classes of error:
    JSON Schema catches structural issues with rich error messages;
    Pydantic catches type-narrowing issues and gives clean Python objects.
    """
    raw = yaml.safe_load(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError(f"Framework YAML must be a top-level mapping; got {type(raw).__name__}")
    _validate_against_schema(raw)
    return Framework.model_validate(raw)


def load_all() -> dict[str, Framework]:
    """Load every framework YAML under FRAMEWORKS_ROOT, keyed by id.

    Skips `_schema.yaml`. Raises if two frameworks share an id, or if any
    YAML fails validation.
    """
    out: dict[str, Framework] = {}
    if not FRAMEWORKS_ROOT.exists():
        return out
    for yaml_path in sorted(FRAMEWORKS_ROOT.rglob("*.yaml")):
        if yaml_path.name == "_schema.yaml":
            continue
        fw = load_framework(yaml_path)
        if fw.id in out:
            raise ValueError(f"Duplicate framework id: {fw.id!r} (at {yaml_path} and earlier)")
        out[fw.id] = fw
    return out
