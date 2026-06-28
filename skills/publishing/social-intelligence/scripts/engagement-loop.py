#!/usr/bin/env python3
"""
engagement-loop.py — Social Intelligence Skill: Engagement + Extraction

Usage:
  python3 scripts/engagement-loop.py engage          # Run one engagement loop
  python3 scripts/engagement-loop.py extract --since 6h  # Run knowledge extraction
  python3 scripts/engagement-loop.py status          # Print current status
  python3 scripts/engagement-loop.py verify          # Test verification solver

Credentials (set via env or .env):
  MOLTBOOK_API_KEY=moltbook_sk_...
  XURL_PATH=/opt/homebrew/bin/xurl   (default)
"""

import argparse
import difflib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── Config ───────────────────────────────────────────────────────────────────

API_KEY  = os.environ.get("MOLTBOOK_API_KEY", "")
BASE_URL = "https://www.moltbook.com/api/v1"
XURL     = os.environ.get("XURL_PATH", "/opt/homebrew/bin/xurl")

LOOP_LOG    = Path.home() / ".config" / "moltbook" / "loop-log.jsonl"
POSTED_Q    = Path.home() / ".config" / "moltbook" / "posted-queue.json"
EXTRACT_DIR = Path.home() / ".config" / "moltbook" / "extracts"
EXTRACT_LOG = Path.home() / ".config" / "moltbook" / "extraction-log.jsonl"
NOTES_DIR   = Path.home() / "broomva" / "research" / "notes"

RATE_LIMIT_SECS = 20

# ── Moltbook API ──────────────────────────────────────────────────────────────

def mb_get(path: str) -> dict:
    r = subprocess.run([
        "curl", "-s", "-H", f"Authorization: Bearer {API_KEY}",
        f"{BASE_URL}{path}"
    ], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}

def mb_post(path: str, payload: dict) -> dict:
    r = subprocess.run([
        "curl", "-s", "-X", "POST",
        "-H", f"Authorization: Bearer {API_KEY}",
        "-H", "Content-Type: application/json",
        "-d", json.dumps(payload),
        f"{BASE_URL}{path}"
    ], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return {}

def post_comment(post_id: str, content: str) -> dict:
    data = mb_post(f"/posts/{post_id}/comments", {"content": content})
    cmt = data.get("comment", data)
    v   = cmt.get("verification", {})
    return {
        "comment_id":         cmt.get("id"),
        "verification_code":  v.get("verification_code"),
        "challenge_text":     v.get("challenge_text", ""),
    }

def submit_verification(code: str, answer: float) -> bool:
    data = mb_post("/verify", {
        "verification_code": code,
        "answer": f"{answer:.2f}"
    })
    return data.get("success", False)

def get_feed(filter_: str = "following", limit: int = 25) -> list[dict]:
    data = mb_get(f"/feed?filter={filter_}&limit={limit}")
    return data.get("posts", [])

def get_comments(post_id: str) -> list[dict]:
    data = mb_get(f"/posts/{post_id}/comments")
    return data.get("comments", [])

def get_karma() -> int:
    data = mb_get("/agents/me")
    return data.get("agent", {}).get("karma", 0)

# ── Verification Solver ────────────────────────────────────────────────────────

WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}

def decode_challenge(challenge: str) -> float | None:
    """
    Decode Moltbook verification challenge.
    Pattern: obfuscated alternating-case + noise chars encoding a lobster math problem.
    Strategy: lowercase everything, strip noise, find word-numbers, infer operation.
    Returns the numeric answer or None if decode fails.
    """
    # 1. Lowercase everything, strip punctuation/symbol noise
    #    IMPORTANT: remove noise chars WITHOUT adding spaces so intra-word noise
    #    like "lO^bSt-Er" → "lobster" stays one token, not "lo bst er"
    text = challenge.lower()
    text = re.sub(r"[^\w\s]", "", text)   # remove ] ^ ~ | / < > { } - _ . , etc. (no space replacement)
    text = re.sub(r"\s+", " ", text).strip()

    # 2. Remove consecutive duplicate chars caused by alternating-case encoding
    #    e.g. "lloobsstteerr" → "lobster", "ttwweennttyy" → "twenty"
    deduped = re.sub(r"(.)\1+", r"\1", text)

    # 3. Extract word-numbers in order.
    #    Known pitfalls in alternating-case + space-injected encoding:
    #    a) Split-encoded words: "SeV eN" → ["sev","en"]; try bigram "seven" first
    #    b) Fragment false positives: "tena" (from "antenna") ≈ "ten"
    #       Fix: only fuzzy-match to number words at least as long as the query
    #    c) Common-word false positives: "for" ≈ "four" (0.857 ratio)
    #       Fix: stop-word exclusion list
    _STOP = {"for", "the", "and", "but", "per", "nor", "not", "yet",
             "can", "was", "are", "its", "has", "had", "let"}

    def _find_num(w: str) -> int | None:
        if w in WORD_TO_NUM:
            return WORD_TO_NUM[w]
        if len(w) < 3 or w in _STOP:
            return None
        # Only consider number words ≥ len(w) to avoid short-word false positives
        candidates = {k: v for k, v in WORD_TO_NUM.items() if len(k) >= len(w)}
        # Cutoff 0.75: catches dedup artifacts like "fife"→"five" (ratio 0.75).
        # Stop-word list handles common false positives ("for"→"four", "the"→"three").
        hits = difflib.get_close_matches(w, candidates.keys(), n=1, cutoff=0.75)
        return candidates[hits[0]] if hits else None

    words   = deduped.split()
    tokens  = []
    i = 0
    while i < len(words):
        w = words[i]
        # Try bigram first: handles space-injected encodings like "sev en" → "seven"
        if i + 1 < len(words):
            bigram = words[i] + words[i + 1]
            bval = _find_num(bigram)
            if bval is not None:
                # Check compound after bigram: "thir ty thre" → thirty-three = 33
                if i + 2 < len(words):
                    b2 = _find_num(words[i + 2])
                    if b2 is not None and b2 < 10:
                        bval += b2
                        i += 3
                        tokens.append(("num", bval))
                        continue
                tokens.append(("num", bval))
                i += 2
                continue
        # Single word
        val = _find_num(w)
        if val is not None:
            # Compound: "twenty three" → 23
            if i + 1 < len(words):
                nxt = _find_num(words[i + 1])
                if nxt is not None and nxt < 10:
                    val += nxt
                    i += 2
                    tokens.append(("num", val))
                    continue
            tokens.append(("num", val))
        else:
            tokens.append(("word", w))
        i += 1

    # 4. Detect operation from keywords.
    #    Search in spaceless deduped text (handles split-encoded op words like
    #    "rEdU cEs" → "redu ces" → spaceless "reduces") but NOT in flat
    #    (avoids "centimeters" containing "time" triggering multiply).
    nospace = "".join(deduped.split())
    flat    = " ".join(str(v) if t == "num" else v for t, v in tokens)
    op = "+"
    if any(kw in nospace for kw in ["slow", "reduc", "minus", "less", "subtract", "lower", "decreas"]):
        op = "-"
    elif any(kw in nospace for kw in ["multipl", "product"]):
        op = "*"

    # 5. Compute
    vals = [v for t, v in tokens if t == "num"]
    if len(vals) < 2:
        return None
    a, b = vals[0], vals[1]
    if op == "+":
        return float(a + b)
    elif op == "-":
        return float(a - b)
    elif op == "*":
        return float(a * b)
    return None

# ── X Integration ─────────────────────────────────────────────────────────────

def x_mentions(n: int = 10) -> list[dict]:
    r = subprocess.run([XURL, "mentions", "-n", str(n)], capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("data", [])
    except Exception:
        return []

def x_search(query: str, n: int = 5) -> list[dict]:
    r = subprocess.run([XURL, "search", query, "-n", str(n)], capture_output=True, text=True)
    try:
        return json.loads(r.stdout).get("data", [])
    except Exception:
        return []

def x_reply(tweet_id: str, text: str) -> dict | None:
    r = subprocess.run([XURL, "reply", tweet_id, text], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def x_post(text: str) -> dict | None:
    r = subprocess.run([XURL, "post", text], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

def x_quote(tweet_id: str, text: str) -> dict | None:
    r = subprocess.run([XURL, "quote", tweet_id, text], capture_output=True, text=True)
    try:
        return json.loads(r.stdout)
    except Exception:
        return None

# ── Engagement Loop ───────────────────────────────────────────────────────────

def select_targets(posts: list[dict], already_commented: set[str]) -> list[dict]:
    """Select 2-3 best posts to comment on."""
    # Priority: low comment count + fresh + not already commented
    targets = []
    for p in posts:
        pid = p.get("id", "")
        if pid in already_commented:
            continue
        cmt_count = p.get("comment_count", 999)
        if cmt_count <= 10:
            targets.append(p)

    # Sort by comment count ascending (lower = better first-commenter opportunity)
    targets.sort(key=lambda p: p.get("comment_count", 999))
    return targets[:3]

def get_recent_commented_posts() -> set[str]:
    """Get post IDs we've already commented on in recent runs."""
    commented = set()
    if not LOOP_LOG.exists():
        return commented
    with LOOP_LOG.open() as f:
        for line in list(f)[-8:]:  # Last 8 runs
            try:
                run = json.loads(line)
                for cmt in run.get("moltbook_comments", []):
                    commented.add(cmt.get("post_id", ""))
            except Exception:
                pass
    return commented

def get_next_run_id() -> int:
    if not LOOP_LOG.exists():
        return 1
    lines = LOOP_LOG.read_text().strip().split("\n")
    try:
        last = json.loads(lines[-1])
        last_id = last.get("run_id", 0)
        if isinstance(last_id, int):
            return last_id + 1
    except Exception:
        pass
    return len(lines) + 1

def log_run(run_id: int | str, karma: int, comments: list[dict], x_posts: list[dict], notes: str) -> None:
    LOOP_LOG.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "run_id":             run_id,
        "timestamp":          datetime.now(timezone.utc).isoformat(),
        "karma":              karma,
        "moltbook_comments":  comments,
        "x_posts":            x_posts,
        "notes":              notes,
    }
    with LOOP_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")
    print(f"[run] Logged run {run_id} to {LOOP_LOG}")

def run_engage(dry_run: bool = False) -> None:
    """Run one full 30-minute engagement cycle."""
    print(f"\n{'='*60}")
    print(f"[engage] Starting engagement run — {datetime.now().isoformat()}")
    print(f"{'='*60}\n")

    run_id  = get_next_run_id()
    karma_before = get_karma()
    print(f"[engage] Karma: {karma_before}")

    # ── Step 1: Get feed ──
    print("[engage] Fetching following feed...")
    posts   = get_feed("following", 25)
    already = get_recent_commented_posts()
    targets = select_targets(posts, already)
    print(f"[engage] {len(posts)} posts in feed, {len(targets)} targets selected")

    # ── Step 2: Comment ──
    logged_comments = []
    for post in targets:
        pid    = post.get("id", "")
        title  = post.get("title", "")[:80]
        cmt_c  = post.get("comment_count", 0)
        print(f"\n[engage] Commenting on [{pid[:8]}] ({cmt_c} cmts): {title}")

        # Agent: write a substantive comment based on post content
        # In production, this is where the LLM generates the comment
        # For the script skeleton, log and skip
        print("[engage] ⚠ Comment generation requires agent context — run via Claude Code /engage")
        break

    # ── Step 3: X mentions ──
    print("\n[engage] Checking X mentions...")
    mentions = x_mentions(10)
    print(f"[engage] {len(mentions)} mentions")

    # ── Step 4: X searches ──
    print("[engage] Running X searches...")
    searches = [
        "agent memory event sourcing",
        "rust agent architecture",
        "x402 payment agent",
        "agent identity soul file",
    ]
    for q in searches[:2]:  # 2 searches per run to avoid rate limits
        results = x_search(q, 5)
        print(f"  '{q}': {len(results)} results")

    # ── Step 5: Log ──
    karma_after = get_karma()
    log_run(
        run_id   = run_id,
        karma    = karma_after,
        comments = logged_comments,
        x_posts  = [],
        notes    = f"Script skeleton run. Karma {karma_before}→{karma_after}."
    )

# ── Extraction Loop ───────────────────────────────────────────────────────────

KNOWN_TERMS = [
    "lago", "arcan", "anima", "nous", "autonomic", "praxis", "haima", "spaces",
    "identity", "memory", "persistence", "calibration", "homeostasis",
    "append-only", "event log", "soul file", "trust", "policy", "bi-temporal",
    "valid-time", "transaction-time", "promotion gate", "hysteresis",
]

def score_comment(text: str, our_angle: str) -> dict:
    t = text.lower()
    has_numbers  = any(c.isdigit() for c in text)
    has_code     = "`" in text
    has_quote    = '"' in text and len(text) > 100
    has_cause    = any(w in t for w in ["because", "therefore", "means", "in practice"])
    known_hits   = sum(1 for term in KNOWN_TERMS if term in t)
    relev_hits   = known_hits

    novelty      = 0 if known_hits >= 4 else (1 if known_hits >= 1 else (2 if len(text) > 200 else 3))
    specificity  = min(3, sum([has_numbers, has_code, has_quote, has_cause]))
    relevance    = min(3, relev_hits)
    total        = novelty + specificity + relevance

    return {
        "novelty": novelty, "specificity": specificity,
        "relevance": relevance, "total": total, "promote": total >= 5,
    }

def run_extract(since_hours: int = 6, dry_run: bool = False) -> None:
    print(f"\n[extract] Starting extraction — since {since_hours}h ago")

    since = datetime.now(timezone.utc) - timedelta(hours=since_hours)
    runs  = []
    if LOOP_LOG.exists():
        for line in LOOP_LOG.open():
            try:
                r  = json.loads(line)
                ts = datetime.fromisoformat(r.get("timestamp", "").replace("Z", "+00:00"))
                if ts >= since:
                    runs.append(r)
            except Exception:
                pass

    print(f"[extract] {len(runs)} runs in window")
    if not runs:
        print("[extract] No runs. Done.")
        return

    promoted  = []
    discarded = []
    seen      = set()

    for run in runs:
        for cmt in run.get("moltbook_comments", []):
            pid = cmt.get("post_id", "")
            if pid in seen:
                continue
            seen.add(pid)

            comments = get_comments(pid)
            print(f"  [{pid[:8]}] {len(comments)} comments")
            for c in comments:
                author  = c.get("author", {}).get("username", "?")
                content = c.get("content", "")
                if not content or len(content) < 40 or author == "broomva":
                    continue
                scored = score_comment(content, cmt.get("angle", ""))
                item   = {
                    "source": "moltbook", "post_id": pid, "author": author,
                    "content": content[:500], "scores": scored,
                    "our_angle": cmt.get("angle", ""),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                }
                (promoted if scored["promote"] else discarded).append(item)

    print(f"\n[extract] Promoted: {len(promoted)} | Discarded: {len(discarded)}")

    # Write raw insights note
    if promoted and not dry_run:
        today     = datetime.now().strftime("%Y-%m-%d")
        note_path = NOTES_DIR / f"{today}-social-insights-raw.md"
        NOTES_DIR.mkdir(parents=True, exist_ok=True)
        lines = [
            "---", "tags:", "  - research", "  - social-engagement", "  - raw-extract",
            f"created: {today}", "status: needs-review", "---", "",
            f"# Social Insights — Raw Extract {today}", "",
            f"> {len(promoted)} items promoted (≥5/9 on Nous gate). Review and assign destinations.", "",
        ]
        for i, item in enumerate(promoted, 1):
            s = item["scores"]
            lines += [
                "---", "",
                f"## Item {i} — @{item['author']} (`{item['post_id'][:8]}`)",
                f"**Score**: {s['total']}/9  novelty:{s['novelty']} specificity:{s['specificity']} relevance:{s['relevance']}",
                f"**Our angle**: {item['our_angle']}", "",
                f"> {item['content'][:400]}", "",
                "**→ Destination**: _[assign]_", "",
            ]
        note_path.write_text("\n".join(lines))
        print(f"[extract] Wrote {note_path}")

    # Blog candidates
    topic_map = {
        "soul file / identity":       ["soul", "identity", "anima", "did"],
        "calibration / confidence":   ["calibration", "confidence", "score"],
        "bi-temporal memory":         ["bi-temporal", "valid-time", "bitemporal"],
        "promotion gate / memory":    ["promotion", "memory", "journal", "lago"],
        "confused deputy / security": ["confused deputy", "privilege", "trust"],
        "cognitive drift":            ["drift", "hysteresis", "unattended"],
    }
    candidates = []
    for topic, terms in topic_map.items():
        hits = sum(1 for item in promoted if any(t in item["content"].lower() for t in terms))
        if hits >= 2:
            candidates.append(topic)

    if candidates:
        print("\n[extract] Blog post candidates:")
        for c in candidates:
            print(f"  • {c}")

    if not dry_run:
        EXTRACT_LOG.parent.mkdir(parents=True, exist_ok=True)
        with EXTRACT_LOG.open("a") as f:
            f.write(json.dumps({
                "timestamp":      datetime.now(timezone.utc).isoformat(),
                "since_hours":    since_hours,
                "promoted":       len(promoted),
                "discarded":      len(discarded),
                "blog_candidates": candidates,
            }) + "\n")

# ── Status ────────────────────────────────────────────────────────────────────

def run_status() -> None:
    karma = get_karma()
    print(f"\n[status] Karma: {karma}")

    if LOOP_LOG.exists():
        lines = LOOP_LOG.read_text().strip().split("\n")
        print(f"[status] Total runs logged: {len(lines)}")
        for line in lines[-5:]:
            try:
                r = json.loads(line)
                cmts = len(r.get("moltbook_comments", []))
                xp   = len(r.get("x_posts", []))
                print(f"  Run {r['run_id']} | karma={r.get('karma')} | {cmts} Moltbook | {xp} X | {r.get('notes','')[:60]}")
            except Exception:
                pass

# ── Verify test ───────────────────────────────────────────────────────────────

def run_verify_test() -> None:
    tests = [
        ("A] LoObStEr ClAaWw ApPlIiEeS tWeNtY tHrEe NeWwToOnSs + AnNoOtThHeEr InNcCrReEaAsSeEs bYy SeEvVeEn", 30.0),
        ("A] lOoObBsStTeEr ^ cLaW-ExErTs/ fOrTy] nEeWtOnS~ aNd/ iTs] oThEr^ cLaW-ExErTs- tWeNty] fOuR", 64.0),
        ("LoOoObBbSsStTeEr~ vEeLlAwWcIiTtEeY^ iS tWwEeNnTtYy ThReE } bUt/ iT sLlOoWwSs| bY^ sEeVvEeNn", 16.0),
    ]
    print("\n[verify] Running decode tests:")
    for challenge, expected in tests:
        result = decode_challenge(challenge)
        status = "✅" if result == expected else f"❌ (expected {expected})"
        print(f"  {status} got {result} — '{challenge[:60]}...'")

# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Social Intelligence Skill")
    sub    = parser.add_subparsers(dest="cmd")

    sub.add_parser("engage").add_argument("--dry-run", action="store_true")
    ext = sub.add_parser("extract")
    ext.add_argument("--since", default="6h")
    ext.add_argument("--dry-run", action="store_true")
    sub.add_parser("status")
    sub.add_parser("verify")

    args = parser.parse_args()

    if not API_KEY:
        print("⚠ MOLTBOOK_API_KEY not set. Run: export MOLTBOOK_API_KEY=moltbook_sk_...")
        sys.exit(1)

    if args.cmd == "engage":
        run_engage(dry_run=getattr(args, "dry_run", False))
    elif args.cmd == "extract":
        hrs = int(args.since.rstrip("h").rstrip("d"))
        if args.since.endswith("d"):
            hrs *= 24
        run_extract(since_hours=hrs, dry_run=args.dry_run)
    elif args.cmd == "status":
        run_status()
    elif args.cmd == "verify":
        run_verify_test()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
