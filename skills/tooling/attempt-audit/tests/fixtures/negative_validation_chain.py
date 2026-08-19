def failure_reason(frames_raw, kept, sheet):
    """Every guard runs; None means all checks passed. Must NOT be flagged."""
    if frames_raw <= 0:
        return "no frames could be extracted"
    if kept <= 0:
        return "every extracted frame was discarded"
    if not sheet:
        return "contact sheet could not be built"
    return None
