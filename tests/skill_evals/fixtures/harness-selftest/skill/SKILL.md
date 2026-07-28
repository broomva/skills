---
name: harness-selftest
category: testing
description: >
  Fixture skill. Exists only so the eval harness has an artifact to bind its
  committed replay fixtures to, and so CI grades a real prompt set instead of
  only asserting that an empty fixture set fails. Triggered by the four cases in
  evals/prompts.json and by nothing else. NOT FOR any real task: it does nothing,
  and no agent should ever load it outside tests/skill_evals/.
---

# harness-selftest

This file is the artifact under test for `tests/skill_evals/fixtures/harness-selftest`.

Every committed fixture in `../cases/` carries the SHA-256 of **this file** and of
the `description:` above. Editing either one invalidates all of them — which is the
point: it is the mutation CI performs on every PR to prove the gate can go RED.

If you edited this file on purpose, regenerate the fixtures:

```bash
python3 tests/skill_evals/fixtures/harness-selftest/generate.py
```
