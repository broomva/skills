def is_short(text):
    """The call is in the TEST; the body is a bare constant. Nothing is skipped."""
    if len(text) < 5:
        return True
    return False
