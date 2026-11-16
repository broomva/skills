"""The digest: one fixed record per episode, written by a subagent, checked by code.

A digest is cached per episode in ``digests/<episode id>.json`` against the
episode's content hash, so a rerun only digests sessions that are new or grew.
:func:`validate` is the gate: a digest that fails it is not used, and its
quote must be the user's own words, verbatim from one of the episode's
prompts (whitespace and quote style aside).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import quote_found

KINDS = ("build", "fix", "research", "review", "operations", "planning", "writing", "design", "data",
         "learning", "meta", "personal", "other")
STEERING = ("delegated", "directed", "iterative", "corrective", "exploratory", "conversational")
OUTCOMES = ("shipped", "partial", "answered", "abandoned", "blocked", "unknown")

FIELDS = {
    "episode": str, "hash": str, "goal": str, "topics": list, "kind": str, "steering": str,
    "steering_note": str, "obstacle": (str, type(None)), "resolution": (str, type(None)), "outcome": dict,
    "ideas": list, "quote": (str, type(None)),
}

INSTRUCTIONS = """# Digest instructions (year-in-ai reflect)

You digest one batch file: `batches/batch-NNN.json`. It holds about 25
episodes, each one session a person drove with AI agents: their prompts
verbatim (`prompts[].text`), the agents' trimmed final replies (`replies[]`,
matched by `i`), where the work ran, what was invoked, the correction markers
the code found, and for some sessions a sampled tool trace (`trace_sample`).

For EVERY episode in the batch write `digests/<episode id>.json` (the
`digests/` directory beside `batches/`), exactly this shape:

```json
{
  "episode": "e-1a2b3c4d",
  "hash": "<the episode's hash field, copied>",
  "goal": "what the person was trying to get done, one sentence",
  "topics": ["2-6 short lowercase topics, e.g. 'ledger privacy', 'ci runners'"],
  "kind": "build | fix | research | review | operations | planning | writing | design | data | learning | meta | personal | other",
  "steering": "delegated | directed | iterative | corrective | exploratory | conversational",
  "steering_note": "how the person steered: briefs, constraints, corrections, what they insisted on",
  "obstacle": "the main obstacle, or null",
  "resolution": "how it was resolved (or why it was not), or null",
  "outcome": {"status": "shipped | partial | answered | abandoned | blocked | unknown",
              "evidence": "what shows it: a PR URL, a ticket, a reply saying it merged, or 'none'"},
  "ideas": ["0-5 ideas, opinions or principles the person expressed"],
  "quote": "one short span of the person's own words, copied exactly from a prompt, or null"
}
```

Rules:

- `quote` must be copied character for character from one of that episode's
  `prompts[].text` (never from a reply, a trace or a title). Pick something
  that shows how they think or work, 4-40 words. No secrets, keys, emails,
  phone numbers or client names; use null rather than a risky quote.
- `outcome.status` is `shipped` only with evidence (a merged PR, a reply that
  reports a merge or a deploy). Otherwise use the weaker status that fits.
- Topics and ideas are your words; keep them short and concrete.
- Write nothing else and send nothing anywhere: these files stay on this
  machine. Do not copy episode text into your final message. If you need a
  helper script, put it in `scratch/` beside `digests/` (never `/tmp` or the
  working directory) and delete it when the check passes.
- When done, run `python3 <skill>/scripts/year_in_ai.py reflect check --year <Y> --batch NNN`
  and fix every error it reports before you finish.
"""


def validate(d, episode: Optional[dict]) -> List[str]:
    """Every problem with one digest, as messages. Empty means it may be used."""
    errors: List[str] = []
    if not isinstance(d, dict):
        return ["not a JSON object"]
    if episode is None:
        return [f"no episode {d.get('episode')!r}"]
    for key, kind in FIELDS.items():
        if key not in d:
            errors.append(f"missing field {key!r}")
        elif not isinstance(d[key], kind):
            errors.append(f"field {key!r} has the wrong type")
    if errors:
        return errors
    if d["episode"] != episode["id"]:
        errors.append("episode id does not match")
    if d["hash"] != episode["hash"]:
        errors.append("stale: the episode changed since this digest (hash differs)")
    if not d["goal"].strip() or len(d["goal"]) > 400:
        errors.append("goal must be 1-400 characters")
    if not 1 <= len(d["topics"]) <= 6 or not all(isinstance(t, str) and 0 < len(t) <= 60 for t in d["topics"]):
        errors.append("topics must be 1-6 strings of at most 60 characters")
    if d["kind"] not in KINDS:
        errors.append(f"kind must be one of {', '.join(KINDS)}")
    if d["steering"] not in STEERING:
        errors.append(f"steering must be one of {', '.join(STEERING)}")
    outcome = d["outcome"]
    if outcome.get("status") not in OUTCOMES or not isinstance(outcome.get("evidence"), str):
        errors.append(f"outcome needs status in {', '.join(OUTCOMES)} and a string evidence")
    if len(d["ideas"]) > 5 or not all(isinstance(i, str) and i.strip() for i in d["ideas"]):
        errors.append("ideas must be at most 5 non-empty strings")
    quote = d["quote"]
    if quote is not None:
        if not 3 <= len(quote.strip()) <= 400:
            errors.append("quote must be 3-400 characters")
        elif not quote_found(quote, [p["text"] for p in episode["prompts"]]):
            errors.append("quote is not verbatim from the user's prompts in this episode")
    return errors


def digest_path(outdir: Path, eid: str) -> Path:
    return outdir / "digests" / f"{eid}.json"


def load(outdir: Path, eid: str):
    path = digest_path(outdir, eid)
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return {"_unparseable": True}


def status(outdir: Path, episodes: List[dict], only: Optional[set] = None) -> Tuple[Dict[str, List[str]], List[str], Dict[str, dict]]:
    """``(errors by episode, missing episode ids, valid digests by episode)``."""
    errors: Dict[str, List[str]] = {}
    missing: List[str] = []
    valid: Dict[str, dict] = {}
    for e in episodes:
        if only is not None and e["id"] not in only:
            continue
        d = load(outdir, e["id"])
        if d is None:
            missing.append(e["id"])
            continue
        problems = ["not valid JSON"] if d.get("_unparseable") else validate(d, e)
        if problems:
            errors[e["id"]] = problems
        else:
            valid[e["id"]] = d
    return errors, missing, valid


def pending(outdir: Path, episodes: List[dict]) -> List[str]:
    """Episodes without a valid digest for their current content: what the next batches hold."""
    errors, missing, _valid = status(outdir, episodes)
    redo = set(errors) | set(missing)
    return [e["id"] for e in episodes if e["id"] in redo]
