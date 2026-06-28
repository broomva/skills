"""CLI persistence helpers — engagements/<slug>/{tenant.yaml,journal.jsonl}.

Tenant context is YAML for human-readability + checkin friendliness. Journal
is JSONL for append-only semantics + grep-ability. P6 — both are gitignored
in real engagements; only `engagements/_template/` is checked in.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from core.engagement import Engagement, EngagementJournal
from core.types import TenantContext

# Resolve relative to the project root. Phase 1: assumes CWD is the project
# root. M4 will add a `--workspace` flag for arbitrary roots.
ENGAGEMENTS_ROOT = Path("engagements")


def tenant_path(tenant_slug: str) -> Path:
    return ENGAGEMENTS_ROOT / tenant_slug / "tenant.yaml"


def journal_path(tenant_slug: str) -> Path:
    return ENGAGEMENTS_ROOT / tenant_slug / "journal.jsonl"


def save_tenant(tenant_slug: str, tenant: TenantContext) -> None:
    """Persist TenantContext as YAML."""
    path = tenant_path(tenant_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = tenant.model_dump(mode="json")
    path.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=True))


def load_tenant(tenant_slug: str) -> TenantContext:
    """Load TenantContext from YAML."""
    path = tenant_path(tenant_slug)
    if not path.exists():
        raise FileNotFoundError(
            f"Tenant {tenant_slug!r} not found at {path}. Did you run `phronesis init`?"
        )
    raw = yaml.safe_load(path.read_text())
    return TenantContext.model_validate(raw)


def load_engagement(tenant_slug: str) -> Engagement:
    """Load tenant + journal from disk and assemble an Engagement aggregate."""
    tenant = load_tenant(tenant_slug)
    journal = EngagementJournal.load_jsonl(tenant, journal_path(tenant_slug))
    return Engagement(tenant=tenant, journal=journal)
