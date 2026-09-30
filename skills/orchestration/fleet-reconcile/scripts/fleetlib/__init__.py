"""fleet-reconcile's library. fleet_reconcile.py is the only entry point.

    common     time, paths, the text guard, atomic writes
    config     the per-scope fleet config (~/.config/ctx/fleet.json)
    parsers    one parser per observed surface, pinned to a Claude Code version
    sources    where each surface is read from (commands and files)
    observe    one tick's snapshot of every surface
    classify   the class table (spec §5.4), the overlap pass and the count check
    scheduled  the inventory of scheduled work (report-only seam)
    ledger     the write-ahead ledger (spec §5.7)
    report     the tick report, the ask batch and the labelling sheet
"""
