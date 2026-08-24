def find_first(items, pred):
    """Searched and not found -- nothing was skipped. Must NOT be flagged."""
    for i in items:
        if pred(i):
            return i
    return None
