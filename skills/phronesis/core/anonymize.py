"""Tenant data anonymization for cross-engagement learning.

Per design spec §7.2 (AnonymizationPolicy), engagement extracts that flow
back into the knowledge graph (research/entities/) MUST be stripped of
tenant-identifying markers. The output should read like Bloomberg
"industry color" — preserves learning, identity-free.

This module ships the policy + the redaction function. The
test_anonymization_canary.py test (Phase E.3) is the release gate: any
checkin that lets a tenant marker leak into anonymized output blocks the
push.

Phase 1 implementation: regex-driven, conservative bias toward over-redaction
(false positives are recoverable; false negatives leak tenant data).
Phase 2+ may swap in NER-based name detection once a real engagement
provides ground truth.
"""

from __future__ import annotations

import re
from decimal import Decimal

from pydantic import BaseModel, Field

from core.types import TenantContext


class AnonymizationPolicy(BaseModel):
    """Configuration for the anonymization pass.

    Defaults to strict-by-default: every privacy-relevant transform is on.
    Callers explicitly opt out via False if they need raw text (e.g. for
    a tenant-private archive snapshot).
    """

    strip_tenant_slug: bool = True
    strip_tenant_name: bool = True
    strip_personal_names: bool = True
    replace_currency_with_bands: bool = True
    replace_dates_with_relative: bool = True
    replace_locations_with_regions: bool = True
    redact_terms: list[str] = Field(default_factory=list)


# ----------------------------------------------------------------------------
# Currency band mapping
# ----------------------------------------------------------------------------


_CURRENCY_BANDS: list[tuple[Decimal, str]] = [
    (Decimal("1000"), "sub-low-4-figures USD"),
    (Decimal("10000"), "low-4-figures USD"),
    (Decimal("100000"), "mid-5-figures USD"),
    (Decimal("1000000"), "low-6-figures USD"),
    (Decimal("10000000"), "low-7-figures USD"),
    (Decimal("100000000"), "low-8-figures USD"),
    (Decimal("1000000000"), "low-9-figures USD"),
]


def _currency_band(amount: Decimal) -> str:
    """Bucket a Decimal amount into a Bloomberg-style band string."""
    for ceiling, label in _CURRENCY_BANDS:
        if amount < ceiling:
            return label
    return "9+-figures USD"


_CURRENCY_RE = re.compile(
    r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)(?:\s?([KMB]))?",
    re.IGNORECASE,
)


def _replace_currency(match: re.Match[str]) -> str:
    raw = match.group(1).replace(",", "")
    suffix = (match.group(2) or "").upper()
    multiplier = {"K": Decimal("1e3"), "M": Decimal("1e6"), "B": Decimal("1e9")}.get(
        suffix, Decimal("1")
    )
    try:
        amount = Decimal(raw) * multiplier
    except (ArithmeticError, ValueError):
        return match.group(0)
    return _currency_band(amount)


# ----------------------------------------------------------------------------
# Date relative-replacement
# ----------------------------------------------------------------------------


_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_QUARTER_RE = re.compile(r"\b(\d{4})-Q[1-4]\b")
_YEAR_RE = re.compile(r"\b(20[2-3]\d)\b")  # 2020-2039


def _replace_iso_date(match: re.Match[str]) -> str:
    return "<engagement-date>"


def _replace_quarter(match: re.Match[str]) -> str:
    return "<engagement-quarter>"


def _replace_year(match: re.Match[str]) -> str:
    return "<engagement-year>"


# ----------------------------------------------------------------------------
# Personal-name detection (Phase 1: heuristic — capitalized adjacent words
# with at least one of: a Latin diacritic-bearing char, an honorific prefix,
# or a hyphen). False-negative prone — Phase 2 swaps in spaCy NER.
# ----------------------------------------------------------------------------


_NAME_RE = re.compile(
    r"\b("
    r"(?:Sr\.|Sra\.|Dr\.|Dra\.|Mr\.|Ms\.|Mrs\.)\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+"
    r"(?:\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+)*"
    r"|"
    r"[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑÜ][a-záéíóúñü]+)+"
    r")"
)


# Tokens that look like names but are domain language we want to keep.
# Phase 1 scope: keep frameworks + roles + Latin geographies that aren't
# tenant-specific.
_NAME_ALLOWLIST: set[str] = {
    # Frameworks
    "Wardley Mapping",
    "Three Horizons",
    "Real Options",
    "Value Proposition Canvas",
    "Jobs To Be Done",
    "MIT CISR",
    "Andrew Ng Pipeline",
    "QuantumBlack ML",
    "Lean Canvas",
    "Business Model Canvas",
    "Cost Of Delay",
    "Owner Earnings",
    "Microsoft Responsible AI",
    "Google PAIR",
    "Five Forces",
    "Where To Play How To Win",
    "Forrester Data",
    "Mckinsey 7S",
    "Mckinsey Influence",
    "Sean Ellis",
    "Sean McBride",
    # Roles (left as-is; the role itself isn't identifying)
    "Head Of Operations",
    "Head Of Customer Service",
    "Head Of Data",
    "Commercial Director",
    "Lead Data Engineer",
    # Regions / public infrastructure (intentionally generic)
    "LATAM",
    "United States",
    "South America",
}


def _replace_name(match: re.Match[str], policy: AnonymizationPolicy) -> str:
    raw = match.group(1)
    if raw in _NAME_ALLOWLIST:
        return raw
    return "<person>"


# ----------------------------------------------------------------------------
# Location detection (Phase 1: explicit list of CO/LATAM cities + country names).
# ----------------------------------------------------------------------------


_LOCATIONS: list[str] = [
    # Colombian cities likely to appear in early engagements
    "Bogotá",
    "Bogota",
    "Medellín",
    "Medellin",
    "Cali",
    "Barranquilla",
    "Cartagena",
    "Bucaramanga",
    # Country names commonly in scope
    "Colombia",
    "Mexico",
    "Brasil",
    "Brazil",
    "Argentina",
    "Chile",
    "Perú",
    "Peru",
]


def _strip_locations(text: str) -> str:
    """Replace specific city/country names with generic LATAM placeholder."""
    pattern = r"\b(" + "|".join(re.escape(loc) for loc in _LOCATIONS) + r")\b"
    return re.sub(pattern, "<latam-region>", text)


# ----------------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------------


def anonymize(
    text: str,
    policy: AnonymizationPolicy,
    tenant: TenantContext,
) -> str:
    """Apply the anonymization policy to `text` for the given tenant.

    Operations applied (in order):
      1. Strip tenant slug + name (literal substring replacement).
      2. Strip caller-supplied redact_terms.
      3. Replace personal names with <person> token.
      4. Replace location names with <latam-region>.
      5. Replace ISO dates / YYYY-Q* / years with relative tokens.
      6. Replace $-prefixed currency with magnitude bands.

    Order matters: dates run before currency because ISO dates contain
    digits that the currency regex would otherwise match-and-corrupt.
    """
    out = text

    if policy.strip_tenant_slug and tenant.tenant_slug:
        out = out.replace(tenant.tenant_slug, "<tenant>")
    if policy.strip_tenant_name and tenant.name:
        out = out.replace(tenant.name, "<tenant>")

    for term in policy.redact_terms:
        if term:
            out = out.replace(term, "<redacted>")

    if policy.strip_personal_names:
        # Strip tenant sponsor name explicitly (more reliable than regex)
        if tenant.sponsor:
            out = out.replace(tenant.sponsor, "<person>")
        out = _NAME_RE.sub(lambda m: _replace_name(m, policy), out)

    if policy.replace_locations_with_regions:
        out = _strip_locations(out)

    if policy.replace_dates_with_relative:
        out = _ISO_DATE_RE.sub(_replace_iso_date, out)
        out = _QUARTER_RE.sub(_replace_quarter, out)
        out = _YEAR_RE.sub(_replace_year, out)

    if policy.replace_currency_with_bands:
        out = _CURRENCY_RE.sub(_replace_currency, out)

    return out


def carries_tenant_marker(text: str, tenant: TenantContext) -> list[str]:
    """Forensic helper: return a list of tenant-identifying markers found
    in `text`. Empty list = clean. Used by the canary test to produce a
    descriptive failure message rather than a bare assertion.
    """
    findings: list[str] = []

    if tenant.tenant_slug and tenant.tenant_slug in text:
        findings.append(f"tenant_slug:{tenant.tenant_slug}")
    if tenant.name and tenant.name in text:
        findings.append(f"tenant_name:{tenant.name}")
    if tenant.sponsor and tenant.sponsor in text:
        findings.append(f"sponsor:{tenant.sponsor}")

    return findings


__all__ = [
    "AnonymizationPolicy",
    "anonymize",
    "carries_tenant_marker",
]
