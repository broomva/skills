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
    r"^#{3,4}\s+(?:(R(\d+)-([QSP])(\d+))|(Seed|Question|Q|Proposal)\s*(\d+))\b\s*[·:—–-]?\s*(.*)$", re.I)
ROUND_RE = re.compile(r"^##\s+Round\s+(\d+)\b", re.I)
FIELD_RE = re.compile(r"^\s*[-*+]\s+\*\*([^*]+?)(?:[:.]\*\*|\*\*\s*:)\s*(.*)$")
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


BULLET_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(.+?)\s*$")


def reference_scan(path: Path) -> tuple[list[str], list[tuple[int, str]], bool]:
    """(names, unread lines, has a references or private-terms heading).

    Names come from any heading that mentions references, and from every bullet
    under a `Private terms` heading. A reference is a bullet `- **Maker** — *Work*
    (year): why` (any bullet marker), or a table row whose first cell is the maker
    and whose second, if italic, is the work. Italics after the first colon are
    description, not names. A bullet or table row in those sections that yields
    no name is returned as unread, so a shape the reader does not know is
    reported rather than skipped."""
    if not path.is_file():
        return [], [], False
    names: list[str] = []
    unread: list[tuple[int, str]] = []
    in_refs = in_private = has_heading = False
    table_row = 0
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if line.startswith("#"):
            low = line.lower()
            in_private = "private terms" in low
            in_refs = "reference" in low and not in_private
            has_heading = has_heading or in_private or in_refs
            table_row = 0
            continue
        stripped = line.strip()
        if in_private:
            m = BULLET_RE.match(line)
            if m:
                term = m.group(1).strip("*_` ")
                (names.append(term) if term else unread.append((n, stripped)))
            continue
        if not in_refs:
            continue
        if stripped.startswith("|"):
            table_row += 1
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if table_row == 1 or all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
                continue  # the header and the separator
            makers, head = cells[0], " ".join(cells[1:2])
        else:
            table_row = 0
            m = BULLET_RE.match(line)
            if not m:
                continue
            bold = re.match(r"^\*\*(.+?)\*\*(.*)$", m.group(1))
            if not bold:
                unread.append((n, stripped))
                continue
            makers, head = bold.group(1), bold.group(2).split(":", 1)[0]
        before = len(names)
        for part in re.split(r",|\band\b|&|/", makers):
            part = part.strip(" *_`")
            if len(part) >= 3:
                names.append(part)
        for title in re.findall(r"(?<!\*)\*([^*]{3,})\*(?!\*)", head):
            names.append(title.strip())
        if len(names) == before:
            unread.append((n, stripped))
    return list(dict.fromkeys(x for x in names if x)), unread, has_heading


def reference_names(path: Path) -> list[str]:
    return reference_scan(path)[0]


def taste_findings(path: Path, rel: str, code: str) -> list[Finding]:
    """What the reader could not read in a taste or style file: unread lines, and
    a references heading that yielded no name at all."""
    names, unread, has_heading = reference_scan(path)
    found = [Finding(code, f"{rel}:{n}", f"cannot read a name from {text[:60]!r}; write '- **Maker** — *Work*' "
                                         "or a table row with the maker in the first cell") for n, text in unread]
    if has_heading and not names and not unread:
        found.append(Finding(code, rel, "has a references or private-terms heading but no name could be read under it"))
    return found


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
# An `### Answers` section with a line that opens "waiting" or "pending" marks the round's
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
                typ = {"seed": "S", "question": "Q", "q": "Q", "proposal": "P"}[word]
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
        if section == "answers" and current is not None \
                and re.match(r"^(waiting|pending)\b", line.strip().strip("*_() "), re.I):
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
        ask_col = column(header, "ask")
        if rnd is None or ask_col is None:
            continue
        ans_col = column(header, "answer")
        q_col = column(header, "question")
        is_questions = q_col is not None
        for line_no, cells in rows:
            if ask_col >= len(cells):
                continue
            ask_id, num = ask_ref(cells[ask_col])
            if "#" in header and header.index("#") < len(cells):
                m = re.match(r"\D*(\d+)", cells[header.index("#")])
                num = int(m.group(1)) if m else num
            state = answer_value(cells[ans_col]) if ans_col is not None and ans_col < len(cells) else ""
            if is_questions and num is not None:
                items.append(Item(f"R{rnd}-Q{num}", rnd, "Q", num, line_no, cells[q_col] if q_col < len(cells) else "",
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


def check_decisions(world: Path, out: list[Finding], complete: bool = False) -> dict[str, str]:
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

    for r, info in sorted(rounds.items()):
        if not any(it.round == r and it.type in "SQ" for it in items):
            out.append(Finding("W12", rel, f"round {r} (line {info['line']}) has no seed or question the checker can read; "
                                           "use '#### R<n>-Q<m>' items, '### Seed <m>' / '### Q<m>' sections, "
                                           "or a table with Ask and Question columns"))
    seeds = [it for it in items if it.round == 0 and it.type == "S"]
    later = [it for it in items if it.round >= 1]
    if later or seeds or complete:
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
    """('decision' | 'evidence' | 'external' | 'unresolved' | 'none', known ids, unknown local ids)."""
    s = source.strip()
    if not s:
        return "none", [], []
    if s.lower().startswith("evidence:"):
        return "evidence", [], []
    known = [k for k in states if re.search(r"(?<![\w-])" + re.escape(k) + r"(?![\w-])", s)]
    # Local ids: item ids (R1-Q2) and round-prefixed ask ids (r1-world-rule). One that
    # resolves to nothing is a typo or a missing record, never an outside authority.
    local = re.findall(r"(?<![\w-])(R\d+-[QSP]\d+|r\d+-[a-z0-9]+(?:-[a-z0-9]+)*)(?![\w-])", s)
    unknown = [r for r in dict.fromkeys(local) if r not in states]
    if unknown:
        return "unresolved", known, unknown
    if known:
        return "decision", known, []
    # Not a local id. A placeholder, or a round or question named some other way,
    # is unresolved; an outside rule must name the file or ledger that holds it.
    if re.match(r"^(pending|tbd|todo|unknown|n/?a|none|\?+)\b", s.lower().strip("*_() ")):
        return "unresolved", [], [s]
    if re.search(r"\bround\s*\d|\b[RQSP]\d+\b", s, re.I):
        return "unresolved", [], [s]
    if not re.search(r"[\w-]+\.(?:ya?ml|md|json|txt|html|toml)\b", s):
        return "unresolved", [], [s]
    return "external", [], []


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
        statement = fact.get("statement")
        if not isinstance(statement, str) or not statement.strip():
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
                out.append(Finding("W03", rel, f"{where}: source {r!r} resolves to nothing: cite a decision or ask id "
                                               "from decisions.md, or the file or ledger that holds an outside rule"))
        if kinds <= {"none"}:
            out.append(Finding("W03", rel, f"{where}: no source; cite the decision or ask it came from"))
        if status == "locked":
            unanswered = [c for c in dict.fromkeys(cited) if states.get(c) != "verbatim"]
            if unanswered:
                out.append(Finding("W04", rel, f"{where}: locked on {', '.join(unanswered)}, which has no verbatim answer"))
            elif "unresolved" in kinds:
                out.append(Finding("W04", rel, f"{where}: locked on a source that resolves to nothing"))
            elif not ({"decision", "external"} & kinds):
                out.append(Finding("W04", rel, f"{where}: locked with no decision behind it (evidence is never a default)"))
        if tier not in SOFT_TIERS and not ({"decision", "external"} & kinds) and "unresolved" not in kinds:
            out.append(Finding("W04", rel, f"{where}: tier {tier} needs a decision or an owner rule as source; evidence alone is apocrypha"))
    return seen


# --- sheets --------------------------------------------------------------------


def sheets(world: Path, folder: str) -> list[Path]:
    """The sheets in a folder: every .md except prompt files (*.prompt.md), which
    may sit beside a sheet and are scanned for W11 only."""
    return sorted(p for p in (world / folder).glob("*.md") if not p.name.endswith(".prompt.md"))


def check_sheet_layout(world: Path, out: list[Finding]) -> None:
    """Sheets live at <folder>/<slug>.md. A sheet in a subfolder would be skipped
    by every check, so it is a finding rather than a silent pass."""
    for folder in ("characters", "locations", "props", "styles"):
        for path in sorted((world / folder).glob("*/**/*.md")):
            if not path.name.endswith(".prompt.md"):
                out.append(Finding("W09", str(path.relative_to(world)),
                                   f"sheets live at {folder}/<slug>.md; this file is in a subfolder and is not checked"))


def check_characters(world: Path, canon_ids: set[str], cap: int, out: list[Finding]) -> None:
    for path in sheets(world, "characters"):
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
            if not name:
                out.append(Finding("W05", rel, "frontmatter has no 'name'; the Fixed DNA must open with it"))
            elif not text.lower().startswith(name.lower()):
                out.append(Finding("W05", rel, f"Fixed DNA should open with the name '{name}:' so a pasted block names its subject"))
        wardrobes = [b for b in blocks if b.kind == "wardrobe"]
        if not any(b.label.split(" ")[0] == "default" for b in wardrobes):
            out.append(Finding("W06", rel, "no ```wardrobe default block (write 'none' inside it for a character who wears nothing)"))
        if str(meta.get("likeness", "")).strip().lower() != "original":
            out.append(Finding("W07", rel, "frontmatter must declare 'likeness: original' (no real person's likeness)"))
        for cid in as_list(meta.get("canon")):
            if canon_ids and cid not in canon_ids:
                out.append(Finding("W03", rel, f"canon id {cid} is not in canon.yaml"))


def check_locations(world: Path, out: list[Finding]) -> None:
    for path in sheets(world, "locations"):
        rel = str(path.relative_to(world))
        _, body = split_frontmatter(path.read_text(encoding="utf-8"))
        blocks = fenced_blocks(body)
        kinds = [b.kind for b in blocks]
        labels = [b.label for b in blocks if b.kind == "state"]
        if any(not label for label in labels):
            out.append(Finding("W15", rel, "a ```state block has no name; write ```state <name> (it becomes states[<name>])"))
        if len(set(labels)) != len(labels):
            out.append(Finding("W15", rel, "two ```state blocks share a name"))
        if "lighting" not in kinds:
            out.append(Finding("W15", rel, "no ```lighting block"))
        if "state" not in kinds:
            out.append(Finding("W15", rel, "no ```state <name> block; a location needs at least one named state"))
        if "description" not in kinds:
            out.append(Finding("W15", rel, "no ```description block"))


def manifest_rows(text: str) -> list[dict]:
    return table_rows(text, ("kind", "slug"))


def column(header: list[str], key: str) -> int | None:
    """The first header cell that starts with key ("Ask ID" answers "ask",
    "Evidence grade" answers "evidence", "Mechanics" answers "mechanic")."""
    for i, cell in enumerate(header):
        if cell.strip("*_` ").lower().startswith(key):
            return i
    return None


def table_rows(text: str, needed: tuple[str, ...]) -> list[dict]:
    """Rows of every Markdown table whose header has a column for each needed key
    (matched by prefix). Each row maps the needed keys, and every raw header
    cell, to its value."""
    rows: list[dict] = []
    header: list[str] | None = None
    index: dict[str, int] = {}
    for line in text.splitlines():
        s = line.strip()
        if not s.startswith("|"):
            header = None
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if header is None:
            found = {k: column(cells, k) for k in needed}
            if all(v is not None for v in found.values()):
                header, index = [c.lower() for c in cells], found
            continue
        if all(re.match(r"^:?-{2,}:?$", c) for c in cells if c):
            continue
        row = dict(zip(header, cells))
        row.update({k: cells[i] if i < len(cells) else "" for k, i in index.items()})
        rows.append(row)
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
        expected = f"{sheet_dir}/{slug}.md" if sheet_dir else None
        declared = row.get("sheet", "").strip("` ")
        if expected and declared and declared != expected:
            out.append(Finding("W09", rel, f"{where}: sheet column says {declared!r}; a {kind} sheet lives at {expected}"))
        target = expected or (declared if declared not in {"", "—", "-"} else None)
        if target and not (world / target).is_file():
            out.append(Finding("W09", rel, f"{where}: no sheet at {target}"))
        if kind == "character":
            raw = row.get("stills", "")
            m = re.match(r"^\s*(\d+)", raw)
            if not m or not STILLS_MIN <= int(m.group(1)) <= STILLS_MAX:
                out.append(Finding("W10", rel, f"{where}: stills {raw!r}; skene locks a character on {STILLS_MIN} to {STILLS_MAX}"))
    for kind, folder in (("character", "characters"), ("location", "locations"), ("prop", "props")):
        for sheet in sheets(world, folder):
            slug = sheet.stem
            if not any((k, slug) in listed for k in ((kind, "ensemble") if kind == "character" else (kind,))):
                out.append(Finding("W09", rel, f"{folder}/{slug}.md has no manifest row; an asset with no entry is never made"))


ACCOUNT_FIELDS = {"role in the world", "platform", "platforms", "platform(s)", "characters"}


def check_accounts(world: Path, out: list[Finding], complete: bool = False) -> None:
    """Every account needs its own non-empty disclosure. An account is a section
    (H2 to H4) that declares an account field (role, platform, characters), or a
    row of a table with Account and Disclosure columns. A complete world has at
    least one account the checker can read."""
    path = world / "accounts.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    sections: list[tuple[str, set[str], bool]] = []
    for line in text.splitlines():
        heading = re.match(r"^#{2,4}\s+(.+)$", line)
        if heading:
            sections.append((heading.group(1).strip(), set(), False))
            continue
        fm = FIELD_RE.match(line)
        if fm and sections:
            name, keys, disclosed = sections[-1]
            key = fm.group(1).strip().lower()
            keys.add(key)
            if key == "disclosure" and fm.group(2).strip():
                disclosed = True
            sections[-1] = (name, keys, disclosed)
    found = 0
    for name, keys, disclosed in sections:
        if keys & ACCOUNT_FIELDS:
            found += 1
            if not disclosed:
                out.append(Finding("W16", "accounts.md", f"account '{name}' has no '**Disclosure:**' line"))
    for row in table_rows(text, ("account", "disclosure")):
        found += 1
        if not row["disclosure"].strip("`*_ —-"):
            out.append(Finding("W16", "accounts.md", f"account '{row['account']}' has an empty disclosure"))
    if complete and not found:
        out.append(Finding("W16", "accounts.md", "no account could be read; give each account a section with "
                                                 "'**Role in the world:**' and '**Disclosure:**' lines"))


def mechanic_matches(used: str, graded: str) -> bool:
    """A format names a mechanic by its full name, or by its first two or more words."""
    words, full = re.findall(r"[\w'-]+", used), re.findall(r"[\w'-]+", graded)
    return words == full or (len(words) >= 2 and full[:len(words)] == words)


def check_mechanics(world: Path, out: list[Finding]) -> None:
    path = world / "accounts.md"
    if not path.is_file():
        return
    text = path.read_text(encoding="utf-8")
    graded: list[str] = []
    for row in table_rows(text, ("mechanic", "evidence")):
        grade = (row.get("evidence", "").strip("` ").lower().split(" ") or [""])[0]
        if grade not in EVIDENCE_GRADES:
            out.append(Finding("W19", "accounts.md", f"mechanic {row.get('mechanic', '?')!r}: evidence {grade!r} is not one of {sorted(EVIDENCE_GRADES)}"))
        else:
            graded.append(row.get("mechanic", "").lower())
    # A format that leans on a mechanic must name one the Mechanics table grades.
    for row in table_rows(text, ("format", "mechanic")):
        cell = row.get("mechanic", "").strip("` ").lower()
        parts = [cell] if any(mechanic_matches(cell, g) for g in graded) else re.split(r"[,;+]", cell)
        for used in parts:
            used = used.strip()
            if used and used not in {"—", "-", "none"} and not any(mechanic_matches(used, g) for g in graded):
                out.append(Finding("W19", "accounts.md", f"format {row.get('format', '?')!r} uses mechanic {used!r}, which no graded Mechanics row names"))


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
    taste_file = taste or world / "owner-taste.md"
    look = world / "styles" / "look.md"
    out.extend(taste_findings(taste_file, "owner-taste.md" if taste is None else str(taste), "W11"))
    out.extend(taste_findings(look, "styles/look.md", "W11"))
    names = list(dict.fromkeys(reference_names(taste_file) + reference_names(look)))
    if not names:
        return
    for where, text in pasted_texts(world):
        for hit in name_hits(text, names):
            out.append(Finding("W11", where, f"taste reference '{hit}' is in a pasted block; references stay in the bible"))


def world_dna_cap(world: Path, out: list[Finding]) -> int:
    path = world / "canon.yaml"
    if not path.is_file():
        return DEFAULT_DNA_CAP
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return DEFAULT_DNA_CAP  # check_canon reports the YAML error
    if not isinstance(data, dict) or "dna_cap" not in data:
        return DEFAULT_DNA_CAP
    cap = data["dna_cap"]
    if isinstance(cap, bool) or not isinstance(cap, int) or cap <= 0:
        out.append(Finding("W02", "canon.yaml", f"dna_cap {cap!r} must be a positive whole number of characters"))
        return DEFAULT_DNA_CAP
    return cap


def check_world(world: Path, complete: bool = False, taste: Path | None = None,
                dna_cap: int | None = None) -> list[Finding]:
    out: list[Finding] = []
    if dna_cap is not None and dna_cap <= 0:
        raise ValueError(f"--dna-cap {dna_cap}: must be a positive number of characters")
    if taste is not None and taste.is_file() and not reference_names(taste):
        raise ValueError(f"--taste {taste}: no reference names or private terms could be read from it")
    if taste is not None and not taste.is_file():
        raise FileNotFoundError(f"--taste {taste}: no such file (an explicit taste file must exist)")
    if complete:
        for name in REQUIRED_FILES:
            if name == "owner-taste.md" and taste is not None:
                continue  # the profile lives outside the world and was passed in
            if not (world / name).is_file():
                out.append(Finding("W18", name, "missing; the output contract needs it"))
        for folder in ("characters", "locations"):
            if not sheets(world, folder):
                out.append(Finding("W18", folder + "/", "empty; the output contract needs at least one sheet"))
    cap = dna_cap if dna_cap is not None else world_dna_cap(world, out)
    states = check_decisions(world, out, complete)
    canon_ids = check_canon(world, states, out)
    if complete and (world / "canon.yaml").is_file() and not canon_ids:
        out.append(Finding("W18", "canon.yaml", "no facts; a complete world has canon"))
    check_characters(world, canon_ids, cap, out)
    check_locations(world, out)
    check_manifest(world, out)
    check_accounts(world, out, complete)
    check_sheet_layout(world, out)
    check_mechanics(world, out)
    check_taste_in_prompts(world, taste, out)
    return out


def check_leak(public: Path, taste: Path) -> list[Finding]:
    names = reference_names(taste)
    out: list[Finding] = taste_findings(taste, taste.name, "L02")
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
        try:
            findings = check_world(args.world, args.complete, args.taste, args.dna_cap)
        except (FileNotFoundError, ValueError) as exc:
            print(exc, file=sys.stderr)
            return 2
        return report(findings, args.json, str(args.world))
    if not args.taste.is_file() or not args.public.is_dir():
        print("leak needs an existing --taste file and public folder", file=sys.stderr)
        return 2
    if not reference_names(args.taste):
        print(f"--taste {args.taste}: no reference names or private terms could be read from it; "
              "nothing would be checked", file=sys.stderr)
        return 2
    return report(check_leak(args.public, args.taste), args.json, f"{args.public} against {args.taste.name}")


if __name__ == "__main__":
    sys.exit(main())
