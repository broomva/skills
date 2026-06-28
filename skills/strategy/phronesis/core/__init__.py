"""phronesis.core — typed primitives at the substrate layer.

This package contains:
- types: atomic primitives (Citation, Score, Finding, Recommendation) and
  deliverable aggregates (UseCase, MaturityDimension, etc.)
- engagement: state model + journal replay (M3)
- stages: stage transitions and review gates (M2)
- linter: P3/P7/P8/L1-L5 enforcement (M3)
- renderer: typed objects → markdown via Jinja2 templates (M3)
- selector: framework_selector primitive (M1)
- extraction: anonymizer + extraction pipeline (M7)

Imports are deferred to subpackages — keep this module empty.
"""

__version__ = "0.1.0-pre"
