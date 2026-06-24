"""swapit-commons — the anonymized household-toxics knowledge commons (reference server).

A small FastAPI service the `swapit` skill syncs to (opt-in). Accepts anonymized knowledge
facts (product / item-class→hazard / alternative), content-addresses + corroborates them,
and serves approved facts back. Deploys to broomva.tech infra (Hostinger VPS / Railway).

Privacy: a server-side backstop rejects any payload carrying an inventory-structural field,
mirroring the client's `anonymize` gate — defense in depth so a buggy client can't leak.
Contributor tokens are hashed, never stored raw.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, ConfigDict

from .privacy import scan_forbidden
from .store import KINDS, Store

MAX_PAYLOAD_BYTES = 32_768  # reject oversized payloads (DoS / abuse guard)


def _db_path() -> str:
    return os.environ.get("SWAPIT_COMMONS_DB", str(Path.home() / ".swapit-commons" / "commons.db"))


store = Store(_db_path())
app = FastAPI(title="swapit-commons", version="0.1.0", description="Anonymized household-toxics knowledge commons")


class Fact(BaseModel):
    model_config = ConfigDict(extra="ignore")  # tolerate client-only keys (schema, created)
    id: str
    kind: str
    payload: dict


@app.get("/health")
def health() -> dict:
    return {"ok": True, **store.stats()}


@app.post("/facts")
def post_fact(fact: Fact, x_anon_token: str | None = Header(default=None)) -> dict:
    if fact.kind not in KINDS:
        raise HTTPException(status_code=400, detail=f"unknown kind '{fact.kind}'")
    if len(json.dumps(fact.payload)) > MAX_PAYLOAD_BYTES:
        raise HTTPException(status_code=413, detail="payload too large")
    leaks = scan_forbidden(fact.payload)
    if leaks:
        raise HTTPException(status_code=422, detail={"error": "payload carries forbidden fields", "fields": leaks})
    return store.upsert({"id": fact.id, "kind": fact.kind, "payload": fact.payload}, token=x_anon_token)


@app.get("/facts")
def get_facts(since: str = "", min_corroboration: int = 1) -> list[dict]:
    return store.list_since(since=since, min_corroboration=min_corroboration)
