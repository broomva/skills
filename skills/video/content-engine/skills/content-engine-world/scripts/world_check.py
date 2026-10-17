#!/usr/bin/env python3
"""world_check.py: the structural gate for a world built by content-engine-world.

A world is a folder of Markdown and YAML written during a grill: decisions.md,
canon.yaml, characters/, locations/, props/, styles/look.md, accounts.md and
asset-manifest.md (the full contract is references/output-contract.md). This
script checks what can be checked without taste:

  W01-W04  canon.yaml: unique ids, valid tier and status, sources that exist,
           and no locked fact resting on a pending answer or on evidence alone.
           A source cites a decision or ask id, an owner rule outside the world
           (another ledger, a rules file), or `evidence: <path>`
  W05-W07  characters: one Fixed-DNA block within the cap that starts with the
           name, at least one wardrobe, likeness declared original. The cap is
           the owner's choice, not a skene limit (skene sets none): --dna-cap,
           else `dna_cap:` in canon.yaml, else 600
  W08-W10  asset-manifest.md: every entry has a skene library kind, a sheet
           file, and 5-20 stills for a character
  W11      no taste-reference name inside a block that is pasted into a prompt
           or a post
  W12-W14  decisions.md: every item has a verbatim answer or is pending, round 0
           is divergent (4-6 seeds, one stretch) and comes first, and a finished
           round has method notes
  W15      locations have lighting and at least one named state
  W16      every account declares how its posts are disclosed as AI-made
  W17      decision ids are unique
  W18      with --complete, the whole file set exists
  W19      every short-form mechanic in accounts.md carries an evidence grade

`leak` is the public-repo guard: it reads the private owner-taste profile and
fails when one of its reference names or private terms appears in a public
folder (the skill itself). The profile never leaves the private repo; only
this script reads it.

Exit 0 when nothing FAILs, 1 otherwise, 2 on a usage error.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # pragma: no cover - exercised only without PyYAML
    sys.exit("world_check.py needs PyYAML: pip install pyyaml")

DEFAULT_DNA_CAP = 600  # the default the first owner chose; a world may set its own
STILLS_MIN, STILLS_MAX = 5, 20  # skene's lock_identity range for a character

# skene-studio FORMATS.md, "The library": the kinds an entry.json may carry.
LIBRARY_KINDS = {"character", "ensemble", "location", "prop", "sound", "style"}
# Where each kind's sheet lives in the world folder.
SHEET_DIR = {
    "character": "characters",
    "ensemble": "characters",
    "location": "locations",
    "prop": "props",
    "style": "styles",
}
# Canon tiers, hardest first (a world may declare its own under `tiers:`):
# foundation (premise, rules, map; only an owner answer changes it), world
# (places, cast, looks, formats; owner-approved), episode (what happened in a
# post; agents may append, checked against the tiers above), apocrypha (not
# canon: lab parodies, experiments, assets that predate the grill).
DEFAULT_TIERS = ("foundation", "world", "episode", "apocrypha")
TIER_ALIASES = {"1": "foundation", "2": "world", "3": "episode"}
SOFT_TIERS = {"episode", "apocrypha"}
STATUSES = {"draft", "locked", "retired"}
# Fenced-block info words whose text is pasted into a prompt or a post.
PASTED_KINDS = {"fixed-dna", "wardrobe", "description", "lighting", "state", "prompt", "caption"}
REQUIRED_FILES = (
    "owner-taste.md", "decisions.md", "bible.md", "canon.yaml", "styles/look.md",
    "sound.md", "timeline.md", "accounts.md", "asset-manifest.md",
)
# How well a short-form mechanic is supported. A proposal or a low heuristic is
# never presented as proven.
EVIDENCE_GRADES = {"measured", "reported", "heuristic", "proposal"}
SEED_FIELDS = {  # label: accepted field names (lower case)
    "Premise": ("premise",),
    "Hook": ("hook",),
    "Why it fits": ("why it fits", "why it is here"),
    "Short-form fit": ("short-form fit", "why it suits short-form"),
    "Cost": ("cost",),
    "Risk": ("risk", "main risk"),
}

HEADED_RE = re.compile(
    r"^#{3,4}\s+(?:(R(\d+)-([QSP])(\d+))|(Seed|Q|Proposal)\s*(\d+))\b\s*[·:—–-]?\s*(.*)$", re.I)
ROUND_RE = re.compile(r"^##\s+Round\s+(\d+)\b", re.I)
FIELD_RE = re.compile(r"^\s*-\s+\*\*([^*]+?)[:.]\*\*\s*(.*)$")
FENCE_RE = re.compile(r"^(```+|~~~+)\s*([A-Za-z][\w-]*)?(.*)$")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
CANON_ID_RE = re.compile(r"^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$")


@dataclass
class Finding:
    code: str
    path: str
    message: str


@dataclass
class Block:
    kind: str
    label: str
    text: str
    line: int


# --- reading ----------------------------------------------------------------


def split_frontmatter(text: str) -> tuple[dict, str]:
    if not text.startswith("---\n"):
        return {}, text
    end = text.find("\n---", 4)
    if end < 0:
        return {}, text
    try:
        meta = yaml.safe_load(text[4:end]) or {}
    except yaml.YAMLError:
        meta = {}
    return (meta if isinstance(meta, dict) else {}), text[end + 4:]


def fenced_blocks(text: str) -> list[Block]:
    """Every fenced block, with its info word (lower case) and the rest as label."""
    blocks: list[Block] = []
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        m = FENCE_RE.match(lines[i].strip())
        if not m:
            i += 1
            continue
        fence, kind, label = m.group(1), (m.group(2) or "").lower(), m.group(3).strip()
        body: list[str] = []
        j = i + 1
        while j < len(lines) and not lines[j].strip().startswith(fence):
            body.append(lines[j])
            j += 1
        blocks.append(Block(kind, label, "\n".join(body).strip(), i + 1))
        i = j + 1
    return blocks


def flat(text: str) -> str:
    """The block as a prompt sees it: one line, single spaces."""
    return " ".join(text.split())


def reference_names(path: Path) -> list[str]:
    """Names listed as `- **Name**` under any heading that mentions references,
    plus every bullet under a `Private terms` heading."""
    if not path.is_file():
        return []
    names: list[str] = []
    in_refs = in_private = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("#"):
            low = line.lower()
            in_private = "private terms" in low
            in_refs = "reference" in low and not in_private
            continue
        if in_private:
            m = re.match(r"^\s*-\s+(.+?)\s*$", line)
            if m:
                names.append(m.group(1).strip("*` "))
        elif in_refs:
            m = re.match(r"^\s*(?:-|\|(?:[^|]*\|)??)\s*\*\*(.+?)\*\*", line)
            if m:
                for part in re.split(r",|\band\b|&|/", m.group(1)):
                    part = part.strip(" *_")
                    if len(part) >= 3:
                        names.append(part)
            for title in re.findall(r"(?<!\*)\*([^*]{3,})\*(?!\*)", line):
                names.append(title.strip())
    return list(dict.fromkeys(n for n in names if n))


def name_hits(text: str, names: list[str]) -> list[str]:
    hits = []
    for name in names:
        if re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", text, re.I):
            hits.append(name)
    return hits


# --- decisions.md -------------------------------------------------------------
#
# Two record forms are accepted, because both have been used by a live grill:
#   headed items   `#### R1-Q2 — title` (or `### Seed 3 · name`, `### Q7 · name`
#                  inside a round) with `- **Field:**` lines and an
#                  `- **Answer:**` line;
#   tables         a questions table with `Ask` and `Question` columns, and an
#                  answers table with `Ask` and `Answer …` columns, keyed by the
#                  ask id (the Maestro ledger's id, in backticks).
# An `### Answers` section that says "waiting" or "pending" marks the round's
# unanswered items pending.


@dataclass
class Item:
    id: str
    round: int
    type: str  # S seed, Q question, P proposal
    number: int
    line: int
    title: str
    ask_id: str = ""
    fields: dict | None = None
    answer: str = ""  # verbatim | pending | paraphrase | "" (nothing on the item)


def answer_value(value: str, quoted_lines: bool = False) -> str:
    v = value.strip()
    bare = v.strip("*_() ").lower()
    if re.match(r"^(pending|waiting)\b", bare):
        return "pending"
    if quoted_lines or v.startswith(">") or v[:1] in {'"', "“", "«"}:
        return "verbatim"
    return "paraphrase" if v else ""


def table_blocks(lines: list[str]):
    """(start line, header cells lower-cased, [(line, cells)]) per Markdown table."""
    i = 0
    while i < len(lines):
        if lines[i].strip().startswith("|"):
            header = [c.strip().lower() for c in lines[i].strip().strip("|").split("|")]
            rows, j = [], i + 1
            while j < len(lines) and lines[j].strip().startswith("|"):
                cells = [c.strip() for c in lines[j].strip().strip("|").split("|")]
                if not all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
                    rows.append((j + 1, cells))
                j += 1
            yield i + 1, header, rows
            i = j
        else:
            i += 1


def ask_ref(cell: str) -> tuple[str, int | None]:
    tick = re.search(r"`([^`]+)`", cell)
    num = re.search(r"\b[QS]?(\d+)\b", cell.replace(tick.group(0), "") if tick else cell)
    return (tick.group(1) if tick else ""), (int(num.group(1)) if num else None)


def parse_decisions(text: str) -> tuple[list[Item], dict[int, dict]]:
    lines = text.splitlines()
    items: list[Item] = []
    rounds: dict[int, dict] = {}
    by_ask: dict[str, str] = {}
    by_num: dict[tuple[int, int], str] = {}
    ask_by_num: dict[tuple[int, int], str] = {}
    current: int | None = None
    item: Item | None = None
    section = ""
    in_answer = False
    round_at_line: dict[int, int | None] = {}
    for n, line in enumerate(lines, 1):
        round_at_line[n] = current
        rm = ROUND_RE.match(line)
        if rm:
            current = int(rm.group(1))
            round_at_line[n] = current
            rounds.setdefault(current, {"line": n, "notes": False, "waiting": False})
            item, section, in_answer = None, "", False
            continue
        hm = HEADED_RE.match(line)
        if hm and (hm.group(1) or current is not None):
            if hm.group(1):
                rnd, typ, num = int(hm.group(2)), hm.group(3).upper(), int(hm.group(4))
            else:
                word = hm.group(5).lower()
                rnd, num = current, int(hm.group(6))
                typ = {"seed": "S", "q": "Q", "proposal": "P"}[word]
            item = Item(f"R{rnd}-{typ}{num}", rnd, typ, num, n, hm.group(7).strip(), fields={})
            items.append(item)
            section, in_answer = "", False
            continue
        if line.startswith("#"):
            item, in_answer = None, False
            low = line.lower()
            section = "notes" if "method notes" in low else "answers" if re.search(r"#\s*answers\b", low) else ""
            continue
        if section == "notes" and current is not None and re.match(r"^\s*[-*]\s+\S", line):
            rounds[current]["notes"] = True
        if section == "answers" and current is not None and re.search(r"\b(waiting|pending)\b", line, re.I) \
                and not line.strip().startswith("|"):
            rounds[current]["waiting"] = True
        if item is None:
            continue
        fm = FIELD_RE.match(line)
        if fm:
            key, value = fm.group(1).strip(), fm.group(2).strip()
            item.fields[key] = value
            in_answer = key.lower().startswith("answer")
            if in_answer:
                item.answer = answer_value(value)
            elif key.lower() == "ask id":
                item.ask_id = value.strip("` ")
            continue
        if in_answer and line.strip().startswith(">"):
            item.answer = "verbatim"
        elif line.strip():
            in_answer = False

    for start, header, rows in table_blocks(lines):
        rnd = round_at_line.get(start)
        if rnd is None or "ask" not in header:
            continue
        ask_col = header.index("ask")
        ans_col = next((i for i, h in enumerate(header) if h.startswith("answer")), None)
        is_questions = "question" in header
        for line_no, cells in rows:
            if ask_col >= len(cells):
                continue
            ask_id, num = ask_ref(cells[ask_col])
            if "#" in header and header.index("#") < len(cells):
                m = re.match(r"\D*(\d+)", cells[header.index("#")])
                num = int(m.group(1)) if m else num
            state = answer_value(cells[ans_col]) if ans_col is not None and ans_col < len(cells) else ""
            if is_questions and num is not None:
                items.append(Item(f"R{rnd}-Q{num}", rnd, "Q", num, line_no, cells[header.index("question")],
                                  ask_id=ask_id, fields={}, answer=state))
            elif state:
                if ask_id:
                    by_ask[ask_id] = state
                if num is not None:
                    by_num[(rnd, num)] = state
                    if ask_id:
                        ask_by_num[(rnd, num)] = ask_id

    for it in items:
        if not it.ask_id and it.type in "SQ":
            it.ask_id = ask_by_num.get((it.round, it.number), "")
        if not it.answer:
            it.answer = by_ask.get(it.ask_id, "") if it.ask_id else ""
        if not it.answer and it.type in "SQ":
            it.answer = by_num.get((it.round, it.number), "")
        if not it.answer and rounds.get(it.round, {}).get("waiting"):
            it.answer = "pending"
    return items, rounds


def field(item: Item, names: tuple[str, ...]) -> str:
    for key, value in (item.fields or {}).items():
        if key.lower() in names:
            return value
    return ""


def check_decisions(world: Path, out: list[Finding]) -> dict[str, str]:
    """Answer state by item id and by ask id."""
    path = world / "decisions.md"
    if not path.is_file():
        return {}
    rel = "decisions.md"
    items, rounds = parse_decisions(path.read_text(encoding="utf-8"))
    states: dict[str, str] = {}
    for it in items:
        if it.id in states:
            out.append(Finding("W17", rel, f"{it.id} (line {it.line}) is a duplicate decision id"))
            continue
        states[it.id] = it.answer or ("unasked" if it.type == "P" else "missing")
        if it.ask_id:
            states[it.ask_id] = states[it.id]
        if it.type == "P":
            continue  # a proposal is an offer; it needs an answer only once it is asked
        if not it.answer:
            out.append(Finding("W12", rel, f"{it.id} (line {it.line}) has no answer; copy the verbatim answer or write 'pending'"))
        elif it.answer == "paraphrase":
            out.append(Finding("W12", rel, f"{it.id} (line {it.line}) answer is not quoted; copy the owner's words verbatim (> or \"…\") or write 'pending'"))

    seeds = [it for it in items if it.round == 0 and it.type == "S"]
    later = [it for it in items if it.round >= 1]
    if later or seeds:
        if 0 not in rounds:
            out.append(Finding("W13", rel, "no '## Round 0' of divergent seeds; it comes before any convergent question"))
        elif not 4 <= len(seeds) <= 6:
            out.append(Finding("W13", rel, f"round 0 has {len(seeds)} seeds; pitch 4 to 6 genuinely different worlds"))
        stretch = [it for it in seeds if re.match(r"^yes\b", field(it, ("stretch",)), re.I)
                   or re.search(r"stretch|against", it.title, re.I)]
        if seeds and not stretch:
            out.append(Finding("W13", rel, "no round-0 seed is a stretch ('**Stretch:** yes', or 'stretch'/'against' in its title)"))
        for it in seeds:
            missing = [label for label, names in SEED_FIELDS.items() if not field(it, names)]
            if missing:
                out.append(Finding("W13", rel, f"{it.id} lacks {', '.join(missing)}"))
        if seeds and later and min(it.line for it in later) < max(it.line for it in seeds):
            out.append(Finding("W13", rel, "a round-1+ item comes before the last round-0 seed; diverge first, then converge"))
    for r, info in sorted(rounds.items()):
        mine = [it for it in items if it.round == r and it.type in "SQ"]
        if mine and all(it.answer == "verbatim" for it in mine) and not info["notes"]:
            out.append(Finding("W14", rel, f"round {r} is answered but has no '### Method notes' bullet"))
    return states


# --- canon.yaml ----------------------------------------------------------------


def as_list(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value]
    return [s.strip() for s in str(value).split(",") if s.strip()]


def canon_tiers(data: dict) -> tuple[set[str], dict[str, str]]:
    declared = data.get("tiers")
    if isinstance(declared, dict) and declared:
        return {str(k) for k in declared}, {}
    if isinstance(declared, list) and declared:
        return {str(k) for k in declared}, {}
    return set(DEFAULT_TIERS), dict(TIER_ALIASES)


def classify_source(source: str, states: dict[str, str]) -> tuple[str, list[str], list[str]]:
    """('decision' | 'evidence' | 'external' | 'none', known ids cited, unknown R-ids cited)."""
    s = source.strip()
    if not s:
        return "none", [], []
    if s.lower().startswith("evidence:"):
        return "evidence", [], []
    known = [k for k in states if re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", s)]
    unknown = [r for r in re.findall(r"\bR\d+-[QSP]\d+\b", s) if r not in states]
    return ("decision" if known else "external"), known, unknown


def check_canon(world: Path, states: dict[str, str], out: list[Finding]) -> set[str]:
    path = world / "canon.yaml"
    if not path.is_file():
        return set()
    rel = "canon.yaml"
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        out.append(Finding("W02", rel, f"not valid YAML: {exc}"))
        return set()
    facts = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(facts, list):
        out.append(Finding("W02", rel, "needs a 'facts:' list"))
        return set()
    allowed, aliases = canon_tiers(data)
    seen: set[str] = set()
    for n, fact in enumerate(facts, 1):
        if not isinstance(fact, dict):
            out.append(Finding("W02", rel, f"fact #{n} is not a mapping"))
            continue
        fid = str(fact.get("id", "")).strip()
        where = fid or f"fact #{n}"
        if not CANON_ID_RE.match(fid):
            out.append(Finding("W02", rel, f"{where}: id must be lower-case-hyphenated"))
        elif fid in seen:
            out.append(Finding("W01", rel, f"{fid} is used twice"))
        seen.add(fid)
        if not str(fact.get("statement", "")).strip():
            out.append(Finding("W02", rel, f"{where}: empty statement"))
        tier = aliases.get(str(fact.get("tier")), str(fact.get("tier")))
        status = fact.get("status")
        if tier not in allowed:
            out.append(Finding("W02", rel, f"{where}: tier {fact.get('tier')!r} is not one of {sorted(allowed)} (declare 'tiers:' to use your own)"))
        if status not in STATUSES:
            out.append(Finding("W02", rel, f"{where}: status {status!r} is not one of {sorted(STATUSES)}"))
        raw = fact.get("source")
        sources = [str(s) for s in raw] if isinstance(raw, list) else [str(raw or "")]
        kinds, cited = set(), []
        for s in sources:
            kind, known, unknown = classify_source(s, states)
            kinds.add(kind)
            cited += known
            for r in unknown:
                out.append(Finding("W03", rel, f"{where}: source {r} is not in decisions.md"))
        if kinds <= {"none"}:
            out.append(Finding("W03", rel, f"{where}: no source; cite the decision or ask it came from"))
        if status == "locked":
            unanswered = [c for c in dict.fromkeys(cited) if states.get(c) != "verbatim"]
            if unanswered:
                out.append(Finding("W04", rel, f"{where}: locked on {', '.join(unanswered)}, which has no verbatim answer"))
            elif not ({"decision", "external"} & kinds):
                out.append(Finding("W04", rel, f"{where}: locked with no decision behind it (evidence is never a default)"))
        if tier not in SOFT_TIERS and not ({"decision", "external"} & kinds):
            out.append(Finding("W04", rel, f"{where}: tier {tier} needs a decision or an owner rule as source; evidence alone is apocrypha"))
    return seen


# --- sheets --------------------------------------------------------------------


def check_characters(world: Path, canon_ids: set[str], cap: int, out: list[Finding]) -> None:
    for path in sorted((world / "characters").glob("*.md")):
        rel = str(path.relative_to(world))
        meta, body = split_frontmatter(path.read_text(encoding="utf-8"))
        name = str(meta.get("name", "")).strip()
        blocks = fenced_blocks(body)
        dna = [b for b in blocks if b.kind == "fixed-dna"]
        if len(dna) != 1:
            out.append(Finding("W05", rel, f"needs exactly one ```fixed-dna block, found {len(dna)}"))
        else:
            text = flat(dna[0].text)
            if len(text) > cap:
                out.append(Finding("W05", rel, f"Fixed DNA is {len(text)} characters; this world's cap is {cap} (cut in the sheet's cut-priority order)"))
            if name and not text.lower().startswith(name.lower()):
                out.append(Finding("W05", rel, f"Fixed DNA should open with the name '{name}:' so a pasted block names its subject"))
        if not any(b.kind == "wardrobe" for b in blocks):
            out.append(Finding("W06", rel, "no ```wardrobe block (write 'none' inside it for a character who wears nothing)"))
        if str(meta.get("likeness", "")).strip().lower() != "original":
            out.append(Finding("W07", rel, "frontmatter must declare 'likeness: original' (no real person's likeness)"))
        for cid in as_list(meta.get("canon")):
            if canon_ids and cid not in canon_ids:
                out.append(Finding("W03", rel, f"canon id {cid} is not in canon.yaml"))


def check_locations(world: Path, out: list[Finding]) -> None:
    for path in sorted((world / "locations").glob("*.md")):
        rel = str(path.relative_to(world))
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        kinds = [b.kind for b in fenced_blocks(body)]
        if "lighting" not in kinds:
            out.append(Finding("W15", rel, "no ```lighting block"))
        if "state" not in kinds:
            out.append(Finding("W15", rel, "no ```state <name> block; a location needs at least one named state"))
        if "description" not in kinds:
            out.append(Finding("W15", rel, "no ```description block"))


def manifest_rows(text: str) -> list[dict]:
    return table_rows(text, ("kind", "slug"))


def table_rows(text: str, needed: tuple[str, ...]) -> list[dict]:
    """Rows of every Markdown table whose header holds all the needed columns."""
    rows: list[dict] = []
    header: list[str] | None = None
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            low = [c.lower() for c in cells]
            if all(col in low for col in needed):
                header = low
            continue
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue
        rows.append(dict(zip(header, cells)))
    return rows


def check_manifest(world: Path, out: list[Finding]) -> None:
    path = world / "asset-manifest.md"
    if not path.is_file():
        return
    rel = "asset-manifest.md"
    rows = manifest_rows(path.read_text(encoding="utf-8"))
    if not rows:
        out.append(Finding("W08", rel, "no table with 'kind' and 'slug' columns"))
        return
    listed: set[tuple[str, str]] = set()
    for row in rows:
        kind = row.get("kind", "").strip("` ").lower()
        slug = row.get("slug", "").strip("` ")
        where = f"{kind or '?'}/{slug or '?'}"
        if kind not in LIBRARY_KINDS:
            out.append(Finding("W08", rel, f"{where}: kind {kind!r} is not a skene library kind {sorted(LIBRARY_KINDS)}"))
            continue
        if not SLUG_RE.match(slug):
            out.append(Finding("W09", rel, f"{where}: slug must be lower-case-hyphenated"))
            continue
        if (kind, slug) in listed:
            out.append(Finding("W09", rel, f"{where} is listed twice"))
        listed.add((kind, slug))
        sheet_dir = SHEET_DIR.get(kind)
        if sheet_dir:
            sheet = world / sheet_dir / f"{slug}.md"
            if not sheet.is_file():
                out.append(Finding("W09", rel, f"{where}: no sheet at {sheet.relative_to(world)}"))
        if kind == "character":
            raw = row.get("stills", "")
            m = re.match(r"^\s*(\d+)", raw)
            if not m or not STILLS_MIN <= int(m.group(1)) <= STILLS_MAX:
                out.append(Finding("W10", rel, f"{where}: stills {raw!r}; skene locks a character on {STILLS_MIN} to {STILLS_MAX}"))
    for kind, folder in (("character", "characters"), ("location", "locations"), ("prop", "props")):
        for sheet in sorted((world / folder).glob("*.md")):
            slug = sheet.stem
            if not any((k, slug) in listed for k in ((kind, "ensemble") if kind == "character" else (kind,))):
                out.append(Finding("W09", rel, f"{folder}/{slug}.md has no manifest row; an asset with no entry is never made"))


ACCOUNT_FIELDS = {"role in the world", "platform", "platforms", "platform(s)", "characters"}


def check_accounts(world: Path, out: list[Finding]) -> None:
    """An H2 section that declares an account field (role, platform, characters)
    is an account, and needs a non-empty Disclosure line."""
    path = world / "accounts.md"
    if not path.is_file():
        return
    sections: list[tuple[str, set[str], bool]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            sections.append((line[3:].strip(), set(), False))
            continue
        fm = FIELD_RE.match(line)
        if fm and sections:
            name, keys, disclosed = sections[-1]
            key = fm.group(1).strip().lower()
            keys.add(key)
            if key == "disclosure" and fm.group(2).strip():
                disclosed = True
            sections[-1] = (name, keys, disclosed)
    for name, keys, disclosed in sections:
        if keys & ACCOUNT_FIELDS and not disclosed:
            out.append(Finding("W16", "accounts.md", f"account '{name}' has no '**Disclosure:**' line"))


def check_mechanics(world: Path, out: list[Finding]) -> None:
    path = world / "accounts.md"
    if not path.is_file():
        return
    rows = table_rows(path.read_text(encoding="utf-8"), ("mechanic", "evidence"))
    for row in rows:
        grade = row.get("evidence", "").strip("` ").lower().split(" ")[0]
        if grade not in EVIDENCE_GRADES:
            out.append(Finding("W19", "accounts.md", f"mechanic {row.get('mechanic', '?')!r}: evidence {grade!r} is not one of {sorted(EVIDENCE_GRADES)}"))


def pasted_texts(root: Path) -> list[tuple[str, str]]:
    """(where, text) for every block a prompt or post pastes, and every *.prompt.md."""
    found: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*.md")):
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8")
        if path.name.endswith(".prompt.md"):
            found.append((rel, split_frontmatter(text)[1]))
            continue
        for b in fenced_blocks(text):
            if b.kind in PASTED_KINDS:
                found.append((f"{rel}:{b.line} ({b.kind})", b.text))
    return found


def check_taste_in_prompts(world: Path, taste: Path | None, out: list[Finding]) -> None:
    names = reference_names(taste or world / "owner-taste.md") + reference_names(world / "styles" / "look.md")
    names = list(dict.fromkeys(names))
    if not names:
        return
    for where, text in pasted_texts(world):
        for hit in name_hits(text, names):
            out.append(Finding("W11", where, f"taste reference '{hit}' is in a pasted block; references stay in the bible"))


def world_dna_cap(world: Path) -> int:
    path = world / "canon.yaml"
    if path.is_file():
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError:
            return DEFAULT_DNA_CAP
        cap = data.get("dna_cap") if isinstance(data, dict) else None
        if isinstance(cap, int) and cap > 0:
            return cap
    return DEFAULT_DNA_CAP


def check_world(world: Path, complete: bool = False, taste: Path | None = None,
                dna_cap: int | None = None) -> list[Finding]:
    out: list[Finding] = []
    cap = dna_cap or world_dna_cap(world)
    if complete:
        for name in REQUIRED_FILES:
            if not (world / name).is_file():
                out.append(Finding("W18", name, "missing; the output contract needs it"))
        for folder in ("characters", "locations"):
            if not any((world / folder).glob("*.md")):
                out.append(Finding("W18", folder + "/", "empty; the output contract needs at least one sheet"))
    states = check_decisions(world, out)
    canon_ids = check_canon(world, states, out)
    check_characters(world, canon_ids, cap, out)
    check_locations(world, out)
    check_manifest(world, out)
    check_accounts(world, out)
    check_mechanics(world, out)
    check_taste_in_prompts(world, taste, out)
    return out


def check_leak(public: Path, taste: Path) -> list[Finding]:
    names = reference_names(taste)
    out: list[Finding] = []
    for path in sorted(p for p in public.rglob("*") if p.is_file()):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for hit in name_hits(text, names):
            out.append(Finding("L01", str(path.relative_to(public)), f"private taste term '{hit}' appears in a public file"))
    return out


# --- CLI -----------------------------------------------------------------------


def report(findings: list[Finding], as_json: bool, label: str) -> int:
    if as_json:
        print(json.dumps({"verdict": "FAIL" if findings else "PASS", "findings": [asdict(f) for f in findings]}, indent=2))
    else:
        for f in findings:
            print(f"FAIL {f.code} {f.path}: {f.message}")
        print(f"VERDICT: {'FAIL' if findings else 'PASS'} ({len(findings)} finding(s), {label})")
    return 1 if findings else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="check a world folder")
    c.add_argument("world", type=Path)
    c.add_argument("--complete", action="store_true", help="require the whole output contract")
    c.add_argument("--taste", type=Path, help="owner-taste.md, when it lives outside the world folder")
    c.add_argument("--dna-cap", type=int, help="Fixed-DNA cap in characters (default: canon.yaml dna_cap, else 600)")
    c.add_argument("--json", action="store_true")
    lk = sub.add_parser("leak", help="fail if a private taste term appears in a public folder")
    lk.add_argument("public", type=Path)
    lk.add_argument("--taste", type=Path, required=True)
    lk.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.cmd == "check":
        if not args.world.is_dir():
            print(f"not a folder: {args.world}", file=sys.stderr)
            return 2
        return report(check_world(args.world, args.complete, args.taste, args.dna_cap), args.json, str(args.world))
    if not args.taste.is_file() or not args.public.is_dir():
        print("leak needs an existing --taste file and public folder", file=sys.stderr)
        return 2
    return report(check_leak(args.public, args.taste), args.json, f"{args.public} against {args.taste.name}")


if __name__ == "__main__":
    sys.exit(main())
