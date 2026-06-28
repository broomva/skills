# X Thread — Technical Deep Dive: Control Theory for AI Agents

## Thread: 8 Posts

---

### 1/8 — Hook

Hot take: the AI agent industry is recapitulating 50 years of control systems engineering — badly.

We've been applying control theory to LLM agents for the past year. Here's what we learned building 37K lines of Rust infrastructure.

🧵

---

### 2/8 — The Problem

Every agent framework treats the LLM as a "reasoning engine" that "decides" what to do next.

But that's not what's happening. The LLM is generating the next token given a context window. It's a stateless function. It has no memory. No homeostasis. No stability guarantees.

Sound familiar? It's an open-loop controller.

---

### 3/8 — Closing the Loop

In control theory, you close the loop by:

1. Defining a plant (the thing being controlled)
2. Measuring the plant state (sensors)
3. Computing an error signal (setpoint - measurement)
4. Applying a control law (the controller)
5. Feeding results back

We did exactly this for AI agents. The "plant" is the codebase. The "sensors" are test results, lint output, type checks. The "setpoint" is "all harness checks pass."

---

### 4/8 — The Agent State Vector

Every agent in our system has a typed AgentStateVector:

- Operating mode (Explore/Execute/Verify/Recover/AskHuman/Sleep)
- Homeostatic indicators (operational, cognitive, economic health)
- Tick counter with provenance
- Capability set (what tools are available)

Mode transitions are typed. Invalid transitions don't compile. The Rust type system is our first safety shield.

---

### 5/8 — Homeostasis, Not Just Error Handling

Autonomic monitors three pillars:

Operational: CPU/memory/process health → is the agent physically able to work?
Cognitive: progress rate, loop detection, goal proximity → is the agent making progress?
Economic: token spend, cost/benefit ratio → is the agent being efficient?

HysteresisGate prevents mode-flapping (the agent equivalent of a thermostat's dead band).

This is PID control adapted for language model agents.

---

### 6/8 — Event Sourcing as State Estimation

Control systems need accurate state estimation. We use event sourcing.

Lago (our persistence layer) records every agent action as an immutable event. Session state is reconstructed by replaying events — like a Kalman filter, but exact.

Benefits: full auditability, time-travel debugging, branching for parallel exploration, zero hidden state.

---

### 7/8 — The Safety Shield

Control systems have safety interlocks. Ours:

"Do not grant an agent more mutation freedom than your evaluator can reliably judge."

Concrete rules:
- Never mutate evaluator + artifact in same trial
- Budget fails closed (agent stops, not continues)
- Rollback always available (event journal)
- 2 failed retries → human escalation

This is the EGRI (Evaluator-Governed Recursive Improvement) safety law.

---

### 8/8 — The Takeaway

AI agent development IS control systems engineering.

Plant = codebase. Sensor = test suite. Controller = LLM. Actuator = tool calls. Setpoint = passing tests. Feedback = event journal.

The frameworks that win will be the ones that internalize this. We're building ours in Rust because infrastructure should be as reliable as the control systems that run power plants.

37K LOC. 31 crates. 1,000 tests. Open source.

What's your take — are agents controllers or reasoners?

