# Changelog

All notable changes to the tekton skill. Format: Keep a Changelog; versioning: semver.

## [0.2.0] - 2026-07-06

### Added
- Containment/hierarchy: `parent:` on any node + `boundary` type; viewer renders nested
  groups with double-click collapse/expand (C4-style drill-down).
- Lifecycle: `status:` on nodes (`current|target|deprecated`, target dashed = as-is/to-be)
  and Nygard-complete ADR decisions (`context`, `consequences`, `status`, `supersedes`).
- Qualities: NFR nodes with `constrains` edges, dedicated view + detail-panel surfacing.
- Fitness functions: `tekton lint` with `rules:` (`forbid-dep`, `no-cycle`, `layer-order`);
  exit-1, CI-gateable.
- `tests/regressions.sh` — 31 assertions, one per adversarial-review finding.
- `tests/visual-audit.sh` — headless-Chrome geometry QA (overlaps, containment, labels;
  fails on empty captures); Linux/macOS.
- Viewer: edge coordinate-frame fix (ELK INCLUDE_CHILDREN containers), anchor/context
  view pruning, per-view legend, `#<view>` deep links, render-generation race guard.

### Fixed
- Lint silent-pass modes (duplicate ids, bare-string `via`, typo'd selector keys),
  `</script>` DATA breakout, tracebacks on malformed/exotic-typed YAML.

## [0.1.0] - 2026-07-06

### Added
- Initial substrate: typed multi-tier graph (`*.arch.yaml`), 5 views as queries,
  Broomva-styled elkjs viewer, cross-tier `query`, Mermaid fallback embed.
