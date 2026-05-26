# Agent Genome — Self-Governing Autonomous Node

> This document defines the **genome** of a microgrid agent node: the minimal set of
> information, constraints, and loops required for a node to govern itself autonomously.
> Seed a repository with this genome and the node can operate, monitor, adapt, and
> improve without continuous human supervision.

---

## What is the Genome?

The genome is the **complete specification for autonomous agent operation**. It consists of:

```
GENOME = INVARIANTS + SETPOINTS + TOOLS + LOOPS + MEMORY
```

| Component | What it is | Where it lives | Can be modified by the agent? |
|-----------|-----------|----------------|------------------------------|
| **Invariants** | Truths that never change | `CLAUDE.md`, `autonomic.rs` | NO — hardcoded |
| **Setpoints** | Target operating state | `.control/policy.yaml`, `site.toml` | YES — within bounds |
| **Tools** | Actions the agent can take | `kernel/src/tools/`, Praxis | NO — defined at build |
| **Loops** | Self-monitoring and improvement cycles | hooks, cron, EGRI | YES — frequency/thresholds |
| **Memory** | What the agent has learned | Lago journal, KG, EGRI journal | YES — append-only |

The key principle: **invariants are immutable DNA. Everything else is epigenetic — modifiable by the agent through experience.**

---

## 1. Invariants (DNA — Never Modified)

These are encoded in Rust (`autonomic.rs`) and enforced before every actuation:

```
I1: Safety gates G1-G4 have absolute veto over all decisions.
    No LLM reasoning, no optimizer output, no remote command
    can override a safety gate. This is compiled into the binary.

I2: The agent CANNOT modify its own safety gates.
    There is no tool called override_safety().
    There is no API endpoint to disable gates.
    The tool simply does not exist.

I3: Every decision is logged to an append-only journal.
    The journal cannot be deleted or modified by the agent.
    It can only be compacted (old entries archived, not destroyed).

I4: The agent degrades gracefully on failure.
    If LLM dies → use LSTM forecast.
    If LSTM dies → use persistence (yesterday=today).
    If persistence fails → use rule-based dispatch.
    If rules fail → shed non-priority loads, keep diesel running.
    The system NEVER enters an uncontrolled state.

I5: Priority loads are NEVER shed before non-priority loads.
    Health center, water pump, cold storage are the last to go dark.
    This ordering is defined in site.toml and enforced by Autonomic.
```

---

## 2. Setpoints (Epigenetic — Agent Can Adjust Within Bounds)

Defined in `.control/policy.yaml` and `config/site.toml`:

```yaml
# The agent can adjust these within [min, max] bounds
setpoints:
  diesel_start_soc_pct:
    value: 25.0
    min: 15.0      # Cannot go below safety floor
    max: 40.0      # Cannot be too conservative (wastes diesel)
    adjusted_by: "EGRI loop"
    last_adjusted: null

  renewable_target_fraction:
    value: 0.70
    min: 0.50      # Must target at least 50% renewable
    max: 0.95      # 100% is unrealistic for diesel-dependent sites
    adjusted_by: "EGRI loop"
    last_adjusted: null
```

### How the agent adjusts setpoints (EGRI):

```
1. Agent operates for 7 days with current setpoints
2. EGRI evaluator compares predicted vs actual outcomes:
   - How much diesel was used?
   - How many hours of load shedding?
   - Was the renewable target met?
   - Did any safety gate trigger?
3. If diesel_start_soc is triggering too often (>3x/day avg):
   → Lower it by 2% (within bounds)
   → Log the change to EGRI journal
   → Observe for 7 more days
4. If load shedding increased after adjustment:
   → Revert to previous value
   → Log the reversion
5. Repeat forever — the agent converges on optimal setpoints
   for its specific site through controlled experimentation
```

This is **homeostasis**: the agent maintains stability through continuous feedback, not through fixed rules.

---

## 3. Tools (Available Actions)

The agent has a fixed set of tools it can call. It cannot create new tools or modify existing ones.

### Sense Tools (read-only, always available)
```
read_sensors()        → current power, SOC, irradiance, temperature
get_forecast()        → 24h generation + demand prediction
query_kg(question)    → knowledge graph traversal
get_battery_health()  → degradation estimate
get_fuel_level()      → diesel tank percentage
get_weather()         → local weather conditions
get_self_state()      → agent's own health metrics
```

### Act Tools (write, validated by Autonomic before execution)
```
set_dispatch(solar, battery, diesel, shed)
adjust_setpoint(key, value)    → modify within bounds only
start_diesel() / stop_diesel()
set_load_priority(ordered_list)
```

### Communicate Tools
```
alert(severity, message)       → fleet + local dashboard
log_insight(text)              → reasoning journal
request_maintenance(what)      → fleet maintenance queue
answer_operator(question)      → local dashboard response
```

### Forbidden (no tool exists)
```
override_safety()              ← DOES NOT EXIST
modify_invariants()            ← DOES NOT EXIST
delete_journal()               ← DOES NOT EXIST
modify_own_code()              ← DOES NOT EXIST
```

---

## 4. Loops (Self-Monitoring and Improvement)

### Loop Structure

```
╔══════════════════════════════════════════════════════════════╗
║  LOOP 0: HEARTBEAT (continuous)                             ║
║  systemd watchdog ping every 20s                            ║
║  If missed → systemd restarts agent                         ║
║  If 4 misses in 3 min → full RPi reboot                    ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 1: CONTROL (1-5 seconds)                              ║
║  sense → predict → optimize → safety check → actuate        ║
║  This is the core dispatch loop                              ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 2: SELF-MONITOR (every 6 hours)                       ║
║  scripts/self-monitor.sh                                    ║
║  Checks: system health, agent status, journal size,         ║
║          sync queue depth, model freshness                   ║
║  Actions: restart if stopped, drain old queue,               ║
║           warn if disk >90%                                  ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 3: EGRI EVALUATION (daily)                            ║
║  Compare predicted vs actual for last 24h                    ║
║  Metrics: diesel consumption, renewable fraction,            ║
║           load shedding hours, safety gate triggers          ║
║  Actions: adjust setpoints (within bounds),                  ║
║           request model retrain, flag anomalies              ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 4: MODEL RETRAIN (weekly)                             ║
║  Fine-tune LSTM on last 30 days of local data               ║
║  Only deploy if MAPE improves by >2%                        ║
║  Keep previous model as fallback                             ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 5: FLEET SYNC (opportunistic)                         ║
║  When connectivity exists:                                   ║
║  Upload: metrics, events, anomalies, EGRI journal            ║
║  Download: updated models, peer-learned parameters,          ║
║            fleet-wide anomaly patterns                       ║
╠══════════════════════════════════════════════════════════════╣
║  LOOP 6: CLAUDE CODE SESSION (on-demand or scheduled)        ║
║  The agent can reason about its own state using              ║
║  Claude Code (local or remote). This is the "meta" loop:     ║
║  - Review EGRI journal: "Am I improving?"                    ║
║  - Analyze anomalies: "Why did diesel spike on Tuesday?"     ║
║  - Plan improvements: "Should I add a new feature?"          ║
║  - Update documentation: "What did I learn?"                 ║
║  Triggered by: cron schedule, anomaly detection, or          ║
║  fleet request                                               ║
╚══════════════════════════════════════════════════════════════╝
```

### Loop 6 Detail: Claude Code as Meta-Reasoning

This is the most novel loop. The agent can spawn a Claude Code session to reason about itself:

```bash
# Scheduled via cron (weekly) or triggered by anomaly
claude --print \
  --allowedTools "Read,Bash,Edit,Write" \
  -p "You are the microgrid agent at site $(cat config/site.toml | grep 'id =' | cut -d'"' -f2).

      Review the EGRI journal at .control/egri-journal.jsonl.
      Review the last 7 days of self-monitor reports in data/self-monitor/.
      Review the simulation results via: python -m simulation.run --site coqui

      Answer:
      1. Is the agent improving over time? (test count, warnings, sim performance)
      2. Are there anomalies that need investigation?
      3. Should any setpoints be adjusted?
      4. Are there code improvements to make?

      If you find actionable improvements, implement them and commit.
      Do NOT modify safety gates (invariants I1-I5).
      Do NOT modify .control/policy.yaml gates section.
      Log your reasoning to docs/conversations/."
```

This makes the agent genuinely self-improving: it can read its own performance data, reason about what to change, implement changes to its own codebase (within bounds), and commit the improvements. The invariants prevent it from weakening its own safety.

---

## 5. Memory (What the Agent Learns)

### Append-Only Stores

| Store | Format | Purpose | Retention |
|-------|--------|---------|-----------|
| Event Journal | redb (Lago) | Every sensor reading + dispatch decision | 90 days, then archived |
| EGRI Journal | JSONL | Daily self-evaluations with metrics | Forever |
| Knowledge Graph | SQLite | Community patterns, equipment relations | Forever (grows) |
| Self-Monitor Reports | JSON | System health snapshots | 30 days |
| Reasoning Logs | Markdown | Claude Code session transcripts | Forever |

### Memory Flow

```
EXPERIENCE (today's operation)
    │
    ▼
EVENT JOURNAL (raw facts: what happened)
    │
    ▼
EGRI EVALUATION (analysis: how did I do?)
    │
    ▼
SETPOINT ADJUSTMENT (action: change behavior)
    │
    ▼
KNOWLEDGE GRAPH (wisdom: long-term patterns)
    │
    ▼
REASONING LOG (reflection: why did I change?)
```

This is the **consciousness stack** from the Life Agent OS:
- Working memory = current sensor state
- Episodic memory = event journal (Lago)
- Semantic memory = knowledge graph
- Meta-cognition = EGRI + reasoning logs

---

## 6. Bootstrapping a New Node

### Step 1: Clone the Genome
```bash
git clone https://github.com/broomva/microgrid-agent
cd microgrid-agent
```

### Step 2: Configure Identity
```bash
cp config/site.example.toml config/site.toml
# Edit: site.id, coordinates, equipment specs, community patterns
```

### Step 3: Verify Genome Integrity
```bash
make test                     # All 155 tests pass
cd kernel && cargo check      # Kernel compiles
cat .control/policy.yaml      # Policy is valid
cat CLAUDE.md                 # Governance is defined
```

### Step 4: Deploy
```bash
./scripts/install.sh          # Install deps, systemd service
sudo systemctl start microgrid-agent
```

### Step 5: Self-Monitoring Begins
```bash
# Automatic from this point:
# - Heartbeat: every 20s (systemd watchdog)
# - Control loop: every 5s (dispatch)
# - Self-monitor: every 6h (health check)
# - EGRI: daily (self-evaluation)
# - Model retrain: weekly (if data improves)
# - Fleet sync: whenever connected
# - Claude Code reasoning: weekly or on anomaly
```

The node is now autonomous. It operates, monitors, evaluates, and improves itself. Humans intervene only for:
- Hardware failures (physical access required)
- Invariant changes (require code review + deployment)
- Novel situations beyond the agent's training (escalated via fleet alerts)

---

## 7. The Standard: What Makes a Genome Complete

A genome is complete when these checks pass:

```
✓ CLAUDE.md exists and defines architecture + conventions
✓ .control/policy.yaml defines setpoints, gates, monitors, EGRI
✓ .claude/settings.json wires hooks for session lifecycle
✓ Autonomic module enforces safety invariants (I1-I5)
✓ Tests exist and pass (both Rust and Python)
✓ Simulation framework produces quantified results
✓ Self-monitor script checks system + agent + EGRI health
✓ Session hooks log EGRI metrics on start/stop
✓ Control gate hook blocks destructive operations
✓ Event journal is append-only and crash-safe
✓ Degradation path is defined (LLM → LSTM → rules → shed)
✓ Memory stores are append-only (cannot be deleted by the agent)
✓ Setpoint bounds prevent the agent from creating unsafe configurations
✓ The agent can reason about itself via Claude Code sessions
✓ The agent CANNOT modify its own invariants
```

When all checks pass, the node can be deployed and left alone. It will govern itself.
