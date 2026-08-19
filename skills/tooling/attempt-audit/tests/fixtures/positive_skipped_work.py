def load_thing(info, allow_extra, out):
    """The reference shape: a switch skips work, fall-through is indistinguishable."""
    if info.get("cached"):
        hits = parse(info["cached"])
        if hits:
            return join(hits), hits
    if allow_extra:
        hits = expensive(info["src"], out) or fallback(info["src"], out)
        if hits:
            return join(hits), hits
    return "", []
