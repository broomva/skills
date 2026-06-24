"""Swapit commons sync client — push anonymized facts, pull community knowledge.

Offline-first and **opt-in**: nothing leaves the device until `swapit sync --configure`
sets an endpoint and opt-in. Contributions queue locally; `swapit sync --dry-run` shows
exactly what would be sent (the privacy preview). The reference server is
``skills/swapit/commons`` (deployed to broomva.tech infra; deploy gated on explicit go).
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from pathlib import Path

import anonymize
import state


# The hosted commons on broomva.tech (Postgres + Better Auth, rides the Vercel deploy).
# `swapit sync --configure --broomva` points here; the standalone commons/ FastAPI service
# is the self-host alternative.
BROOMVA_COMMONS = "https://broomva.tech/api/swapit"


def config_path() -> Path:
    return state.sync_dir() / "config.json"


def queue_path() -> Path:
    return state.contributions_dir() / "queue.jsonl"


def log_path() -> Path:
    return state.sync_dir() / "sync-log.jsonl"


def load_config() -> dict:
    return state.read_json(
        config_path(), {"endpoint": None, "token": None, "opt_in": False, "last_sync": None}
    )


def save_config(cfg: dict) -> None:
    state.write_json(config_path(), cfg)


def configure(*, endpoint: str | None = None, token: str | None = None, opt_in: bool | None = None) -> dict:
    cfg = load_config()
    if endpoint is not None:
        cfg["endpoint"] = endpoint
    if token is not None:
        cfg["token"] = token
    if opt_in is not None:
        cfg["opt_in"] = opt_in
    save_config(cfg)
    return cfg


# ----------------------------------------------------------------- contribution queue
def enqueue(fact: dict) -> dict:
    anonymize.assert_clean(fact)  # gate at enqueue time too
    state.append_jsonl(queue_path(), fact)
    return fact


def queued() -> list[dict]:
    return state.read_jsonl(queue_path())


def clear_queue() -> None:
    if queue_path().exists():
        queue_path().write_text("", encoding="utf-8")


def dry_run() -> list[dict]:
    """What `sync` would send — each fact with its privacy-scan result."""
    out = []
    for f in queued():
        leaks = anonymize.scan_for_forbidden(f)
        out.append(
            {"id": f["id"], "kind": f["kind"], "clean": not leaks, "leaks": leaks, "payload": f["payload"]}
        )
    return out


# ----------------------------------------------------------------------- http helpers
def _request(url: str, token: str | None, data: dict | None, timeout: int):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Anon-Token"] = token
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, headers=headers, method="POST" if data is not None else "GET")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read() or b"null")


# ----------------------------------------------------------------------- merge (pull)
def _safe_unit(value, default: float = 0.5) -> float:
    """Parse a 0..1 float from untrusted commons payload — never raise, always clamp."""
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


def merge_incoming(facts: list[dict]) -> int:
    """Apply community facts to the local knowledge cache (validate-and-skip).

    Safety rules:
      * a fact referencing an item-class / hazard this client doesn't know is **skipped**
        (never write a broken edge — that would break selfheal + the risk engine);
      * community hazard edges may only **add** a hazard or **raise** its likelihood, never
        lower an existing one — unverified community input must not suppress a safety warning;
      * merged records are tagged ``source: "commons"`` so they're distinguishable from seed.
    """
    kdir = state.knowledge_dir()
    products = {r["id"]: r for r in state.read_jsonl(kdir / "products.jsonl")}
    alternatives = {r["id"]: r for r in state.read_jsonl(kdir / "alternatives.jsonl")}
    classes = {r["id"]: r for r in state.read_jsonl(kdir / "item-classes.jsonl")}
    hazard_ids = {r["id"] for r in state.read_jsonl(kdir / "hazards.jsonl")}
    class_ids = set(classes)
    merged = 0

    for f in facts:
        p = f.get("payload", {})
        conf = _safe_unit(p.get("confidence", 0.5))
        try:
            corro = max(1, int(f.get("corroboration_count", 1) or 1))
        except (TypeError, ValueError):
            corro = 1
        kind = f.get("kind")

        if kind == "product":
            if p.get("item_class") not in class_ids:
                continue  # unknown item-class — can't apply
            products[f["id"]] = {
                "id": f["id"], "name": p.get("product_name"), "brand": p.get("brand"),
                "barcode": p.get("gtin"), "item_class": [p["item_class"]],
                "observed_hazards": [h for h in p.get("observed_hazards", []) if h in hazard_ids],
                "evidence": p.get("evidence", {}), "confidence": conf,
                "corroboration_count": corro, "source": "commons",
            }
            merged += 1
        elif kind == "alternative":
            replaces = [c for c in p.get("replaces", []) if c in class_ids]
            if not p.get("name") or not replaces:
                continue  # no name or no resolvable item-class to replace
            alternatives[f["id"]] = {
                "id": f["id"], "name": p["name"], "replaces": replaces,
                "material": p.get("material", ""), "rationale": p.get("rationale", ""),
                "tradeoffs": [], "caveats": [],
                "avoids_hazards": [h for h in p.get("avoids_hazards", []) if h in hazard_ids],
                "residual_concerns": [], "confidence": conf, "corroboration_count": corro,
                "sources": p.get("sources", []), "source": "commons",
            }
            merged += 1
        elif kind == "item_class_hazard":
            cid, hid = p.get("item_class"), p.get("hazard_id")
            cls = classes.get(cid)
            if cls is None or hid not in hazard_ids:
                continue  # unknown item-class or hazard — skip
            edges = cls.setdefault("hazards", [])
            edge = next((e for e in edges if e.get("hazard_id") == hid), None)
            new_pl = _safe_unit(p.get("presence_likelihood", 0.5))
            if edge is None:  # community may ADD a hazard (more caution)
                edges.append({"hazard_id": hid, "presence_likelihood": new_pl, "rationale": p.get("rationale", ""), "source": "commons"})
                merged += 1
            elif new_pl > float(edge.get("presence_likelihood", 0)):  # may only RAISE, never lower
                edge["presence_likelihood"] = new_pl
                if p.get("rationale"):
                    edge["rationale"] = p["rationale"]
                merged += 1

    _write_jsonl(kdir / "products.jsonl", products.values())
    _write_jsonl(kdir / "alternatives.jsonl", alternatives.values())
    _write_jsonl(kdir / "item-classes.jsonl", classes.values())
    return merged


def _write_jsonl(path: Path, records) -> None:
    path.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8")


# --------------------------------------------------------------------------- push/pull
def _rewrite_queue(facts: list[dict]) -> None:
    queue_path().write_text("".join(json.dumps(f, ensure_ascii=False) + "\n" for f in facts), encoding="utf-8")


def push_pull(timeout: int = 15) -> dict:
    cfg = load_config()
    if not cfg.get("opt_in") or not cfg.get("endpoint"):
        raise RuntimeError("sync not configured — run: swapit sync --configure --endpoint <url> --opt-in")
    base = cfg["endpoint"].rstrip("/")
    token = cfg.get("token")

    pushed, rejected, remaining = 0, [], []
    for fact in queued():
        try:
            anonymize.assert_clean(fact)  # final gate before it leaves the device
            _request(f"{base}/facts", token, fact, timeout)
            pushed += 1
        except anonymize.PrivacyError as exc:
            rejected.append({"fact": fact, "reason": f"privacy: {exc}"})  # never send; quarantine
        except urllib.error.HTTPError as exc:
            rejected.append({"fact": fact, "reason": f"server rejected ({exc.code})"})
        except (urllib.error.URLError, OSError):
            remaining.append(fact)  # network issue — keep for next sync (don't lose it)
    _rewrite_queue(remaining)  # one bad fact can never block the queue forever
    for r in rejected:
        state.append_jsonl(state.contributions_dir() / "quarantine.jsonl", r)

    pulled, merged = [], 0
    try:
        since = cfg.get("last_sync") or ""
        pulled = _request(f"{base}/facts?since={since}", token, None, timeout) or []
        merged = merge_incoming(pulled)
        cfg["last_sync"] = state.now_iso()
        save_config(cfg)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        pass  # pull is best-effort; leave last_sync unchanged so we retry next time

    state.append_jsonl(
        log_path(),
        {"ts": state.now_iso(), "pushed": pushed, "pulled": len(pulled), "merged": merged, "rejected": len(rejected)},
    )
    return {"pushed": pushed, "pulled": len(pulled), "merged": merged, "rejected": len(rejected)}
