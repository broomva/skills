def show_or_disk(sha, path, expected):
    """Skips the git read when `sha` is empty, but then tries disk. Attempted."""
    if sha:
        proc = run(["git", "show", f"{sha}:{path}"])
        if proc.ok and digest(proc.out) == expected:
            return proc.out
    disk = read(path)
    if disk is not None and digest(disk) == expected:
        return disk
    return None
