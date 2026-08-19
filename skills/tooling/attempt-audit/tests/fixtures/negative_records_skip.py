def load_thing(info, allow_extra, out, degradations):
    """Same shape, but the skip is recorded -- honest, must NOT be flagged."""
    if allow_extra:
        hits = expensive(info["src"], out)
        if hits:
            return join(hits), hits
    else:
        degradations.append("extra disabled; transcript unattempted, not empty")
    return "", []
