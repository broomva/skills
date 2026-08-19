def entry_id(entry):
    """The guard tests the SUBJECT, not a switch. None means "no id here"."""
    if isinstance(entry, str) and entry:
        return entry
    if isinstance(entry, dict):
        for k in ("id", "identifier"):
            v = entry.get(k)
            if isinstance(v, str) and v:
                return v
    return None
