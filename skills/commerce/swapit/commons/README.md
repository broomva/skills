# swapit-commons

The anonymized **household-toxics knowledge commons** for the [`swapit`](..) skill. A small
FastAPI service that every user's contributions enrich — *only generic facts ever cross the
boundary; private inventory never does.*

## What it stores

Content-addressed **facts** (one of three kinds):
- `product` — a specific product → item-class mapping (the crowd-sourced product layer)
- `item_class_hazard` — a correction/addition to an item-class → hazard edge
- `alternative` — a safer-alternative suggestion

Identical facts from different users **corroborate** (count up) instead of duplicating. A fact
is served only once it clears the moderation gate (`corroboration >= 2` OR `confidence >= 0.7`)
— the Nous-gate analog. Contributor tokens are hashed, never stored raw.

## Privacy (defense in depth)

The server runs the **same backstop** as the client's `anonymize` gate: any payload carrying an
inventory-structural field (`room`, `quantity`, `usage`, `photos`, `cost`, `checklist`, …) is
rejected with `422`. So even a buggy or malicious client cannot leak who-owns-what.

## API

| Method | Path | Notes |
|---|---|---|
| `GET` | `/health` | liveness + fact counts |
| `POST` | `/facts` | submit a fact (`X-Anon-Token` header optional); upsert + corroborate |
| `GET` | `/facts?since=<iso>&min_corroboration=<n>` | pull approved facts updated since a timestamp |

## Run locally

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8080
# point the skill at it:
swapit sync --configure --endpoint http://127.0.0.1:8080 --opt-in
swapit sync --dry-run      # preview what would be sent (privacy check)
swapit sync                # push queued facts + pull community knowledge
```

## Test

```bash
pip install -r requirements.txt
pytest tests/ -q
```

## Deploy (broomva.tech infra — gated on explicit go)

Storage is a single SQLite file on a mounted volume (`SWAPIT_COMMONS_DB`, default
`/data/commons.db`) so facts survive redeploys.

- **Hostinger VPS** (broomva.tech servers): `docker build -t swapit-commons . && docker run -d -p 8080:8080 -v /srv/swapit-commons:/data swapit-commons`, then reverse-proxy a subdomain (e.g. `commons.swapit.broomva.tech`) to `:8080`.
- **Railway** (the workspace default): the `Procfile` + `requirements.txt` are Nixpacks-ready; add a volume mounted at `/data` and set `SWAPIT_COMMONS_DB=/data/commons.db`.

> The live deploy is intentionally **not** performed in this PR — it needs credentials / DNS.
> The skill is fully functional offline without it; the commons is opt-in.

## Roadmap

- Auth: anonymous tokens today; optional Better-Auth-backed identified contributors later
  (for reputation-weighted corroboration).
- Moderation: corroboration + confidence gate today; a review queue + flagging later.
- `since` is timestamp-based; a cursor/etag model would scale pulls better.
