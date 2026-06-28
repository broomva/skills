"""Server-side privacy denylist — the backstop behind the client's allowlist gate.

This set MUST match the client's ``anonymize.CONTRIBUTION_FORBIDDEN`` exactly. The skill
test ``tests/test_anonymize.py::test_client_server_forbidden_sets_match`` loads this module
and asserts equality, so the two can never silently drift (the failure mode that previously
let a raw ``usage`` dict past the client gate).
"""
from __future__ import annotations

FORBIDDEN = frozenset(
    {
        # item-structural (private — reveal what you own)
        "room", "quantity", "acquired", "notes", "photos", "cost", "vendor",
        "procurer_report_ref", "checklist", "bookmarks",
        # household-behaviour (private — reveal how you live)
        "usage", "food_contact", "heat", "child_contact", "frequency", "status",
        # forward-looking (forbidden if ever introduced)
        "owner", "location", "household", "purchased",
    }
)


def scan_forbidden(obj, path: str = "payload") -> list[str]:
    """Recursively collect dotted paths of forbidden keys (dict / list / tuple / set)."""
    hits: list[str] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k in FORBIDDEN:
                hits.append(f"{path}.{k}")
            hits.extend(scan_forbidden(v, f"{path}.{k}"))
    elif isinstance(obj, (list, tuple, set)):
        for i, v in enumerate(obj):
            hits.extend(scan_forbidden(v, f"{path}[{i}]"))
    return hits
