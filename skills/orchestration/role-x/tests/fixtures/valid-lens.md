---
name: valid-lens
status: active
extends: _meta
signals:
  paths: ["**/*.test"]
  prompt_keywords: ["test"]
  branch_patterns: ["test/*"]
  linear_labels: ["test-label"]
context_loaders:
  files: ["test.md"]
  entities: []
  skills: []
  glob_hints: []
default_mode: augment
quality_bar:
  - "Test passes"
prompt_improvement_patterns: []
mode_escalation:
  rewrite_when: []
  decompose_when: []
out_of_scope: []
related_lenses: []
created: 2026-05-13
updated: 2026-05-13
---

# valid-lens
A valid lens for tests.
