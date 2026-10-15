---
name: fleet-reconcile
tier: D
primitive: null
category: orchestration
deprecated: fleet
description: |
  Deprecated alias of the fleet skill (renamed in fleet 0.6.0, BRO-3122;
  removed after one release). Use fleet; its reconcile workflow is this
  skill's old content.
---

# fleet-reconcile → fleet

This skill is now [`fleet`](../fleet/SKILL.md). The hourly tick it described
is fleet's [reconcile workflow](../fleet/workflows/reconcile.md).

The old paths still run, for one release, and print a deprecation line on
stderr before forwarding:

| Old | Forwards to |
|---|---|
| `skills/orchestration/fleet-reconcile/scripts/fleet` | `skills/orchestration/fleet/scripts/fleet` |
| `skills/orchestration/fleet-reconcile/scripts/install.sh` | `skills/orchestration/fleet/scripts/install.sh` |
| `skills/orchestration/fleet-reconcile/scripts/tick.sh` | `skills/orchestration/fleet/scripts/tick.sh` |

Nothing else lives here. The launchd labels, state and releases directories
keep the `fleet-reconcile` name; see fleet's SKILL.md.
