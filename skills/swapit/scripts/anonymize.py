"""Swapit anonymization — the privacy gate between private inventory and the commons.

The model is **allowlist-by-construction**: a contribution is assembled field-by-field
from explicit, generic inputs (an item-class, a hazard id, a public product name) — never
by serializing a private inventory item. A deep scan then asserts, belt-and-suspenders,
that no *inventory-structural* field leaked in.

Why a tailored denylist (not just ``state.PRIVATE_FIELDS``): on an inventory item, ``name``
and ``brand`` are private (they reveal what *you* own — "Grandma's bottle from Berlin").
But on a *product knowledge fact* those same words are public ("Brand X Cling Film exists and
contains phthalates"), typed deliberately by the contributor. So the contribution-forbidden
set is the structural fields that only ever appear on an owned item — ``room``, ``quantity``,
``usage``, ``photos``, ``cost``, ``checklist`` … — whose presence is a sure sign an inventory
record leaked. ``name``/``brand``/``url``/``title`` carry legitimate public meaning and are
admitted only via the allowlist builders, never copied from an item.
"""
from __future__ import annotations

import hashlib
import json

import state


class PrivacyError(ValueError):
    """Raised when a contribution payload would leak a private inventory field."""


# Inventory-structural fields that must NEVER appear in a contribution (the backstop).
# Derived from the inventory privacy contract, minus the few names with legitimate PUBLIC
# meaning on a knowledge fact (name/brand/url/title), PLUS the household-behaviour signals
# (the `usage` dict, its sub-keys, and item status) — those are private even though they
# aren't on the item-field denylist. The commons server mirrors this exact set
# (commons/app/privacy.py) and tests/test_anonymize.py asserts the two never drift.
_BEHAVIORAL = frozenset({"usage", "food_contact", "heat", "child_contact", "frequency", "status"})
CONTRIBUTION_FORBIDDEN = frozenset((state.PRIVATE_FIELDS - {"name", "brand", "url", "title"}) | _BEHAVIORAL)

# Free-text fields are sent verbatim (they carry legitimate public content like a product
# name). They are the contributor's responsibility — but cap absurd lengths as a sanity guard.
MAX_FREETEXT = 600


def scan_for_forbidden(obj, path: str = "payload") -> list[str]:
    """Return the dotted paths of any forbidden *key* found anywhere in ``obj``.

    Recurses every container (dict / list / tuple / set), so a forbidden field can't hide in
    a non-list container. ``assert_clean`` additionally scans the JSON-serialized form so the
    thing checked is exactly the thing that goes on the wire.
    """
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in CONTRIBUTION_FORBIDDEN:
                hits.append(f"{path}.{k}")
            hits.extend(scan_for_forbidden(v, f"{path}.{k}"))
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            hits.extend(scan_for_forbidden(v, f"{path}[{i}]"))
    return hits


def assert_clean(fact: dict) -> dict:
    try:
        wire = json.loads(json.dumps(fact, ensure_ascii=False))  # exactly what would be sent
    except (TypeError, ValueError) as exc:
        raise PrivacyError(f"contribution is not JSON-serializable: {exc}") from exc
    hits = sorted(set(scan_for_forbidden(wire)) | set(scan_for_forbidden(fact)))
    if hits:
        raise PrivacyError(f"contribution would leak private field(s): {', '.join(hits)}")
    return fact


def _check_freetext(**fields) -> None:
    for name, value in fields.items():
        if isinstance(value, str) and len(value) > MAX_FREETEXT:
            raise PrivacyError(f"free-text field '{name}' exceeds {MAX_FREETEXT} chars — trim it before contributing")


def _content_hash(kind: str, key: dict) -> str:
    """Deterministic id so identical facts dedupe + corroborate. The key includes the full
    semantic content (item-class, hazards) so a *different* mapping is a different fact —
    you cannot corroborate a benign fact and then swap its meaning."""
    blob = json.dumps({"kind": kind, **key}, sort_keys=True, ensure_ascii=False)
    return "fact_" + hashlib.sha256(blob.encode("utf-8")).hexdigest()[:16]


def _finalize(kind: str, key: dict, payload: dict) -> dict:
    fact = {
        "id": _content_hash(kind, key),
        "kind": kind,
        "schema": 1,
        "payload": payload,
        "created": state.now_iso(),
    }
    return assert_clean(fact)  # the gate


# ---- allowlist builders ----------------------------------------------------------
def product_fact(
    *,
    product_name: str,
    item_class: str,
    brand: str | None = None,
    gtin: str | None = None,
    observed_hazards: list[str] | None = None,
    recycling_code: str | None = None,
    label_terms: list[str] | None = None,
    confidence: float = 0.7,
) -> dict:
    """A specific product mapped to an item-class (the crowd-sourced product layer)."""
    _check_freetext(product_name=product_name, brand=brand, gtin=gtin, recycling_code=recycling_code)
    haz = sorted(observed_hazards or [])
    payload = {
        "product_name": product_name,
        "brand": brand,
        "gtin": gtin,
        "item_class": item_class,
        "observed_hazards": haz,
        "evidence": {"recycling_code": recycling_code, "label_terms": label_terms or []},
        "confidence": confidence,
    }
    # hash over the full mapping (incl. item_class + hazards) so a different mapping is a
    # different fact — corroboration cannot swap a product's meaning
    return _finalize("product", {"gtin": gtin, "product_name": product_name, "brand": brand, "item_class": item_class, "observed_hazards": haz}, payload)


def hazard_presence_fact(
    *,
    item_class: str,
    hazard_id: str,
    presence_likelihood: float,
    rationale: str,
    source_url: str | None = None,
    source_title: str | None = None,
    confidence: float = 0.7,
) -> dict:
    """A correction/addition to an item-class → hazard edge."""
    _check_freetext(rationale=rationale, source_url=source_url, source_title=source_title)
    payload = {
        "item_class": item_class,
        "hazard_id": hazard_id,
        "presence_likelihood": presence_likelihood,
        "rationale": rationale,
        "sources": [{"url": source_url, "title": source_title}] if source_url else [],
        "confidence": confidence,
    }
    return _finalize("item_class_hazard", {"item_class": item_class, "hazard_id": hazard_id}, payload)


def alternative_fact(
    *,
    name: str,
    replaces: list[str],
    avoids_hazards: list[str],
    material: str,
    rationale: str,
    source_url: str | None = None,
    confidence: float = 0.7,
) -> dict:
    """A safer-alternative suggestion for one or more item-classes."""
    _check_freetext(name=name, material=material, rationale=rationale, source_url=source_url)
    payload = {
        "name": name,
        "replaces": replaces,
        "avoids_hazards": avoids_hazards,
        "material": material,
        "rationale": rationale,
        "sources": [{"url": source_url}] if source_url else [],
        "confidence": confidence,
    }
    return _finalize("alternative", {"name": name, "replaces": sorted(replaces), "avoids_hazards": sorted(avoids_hazards)}, payload)
