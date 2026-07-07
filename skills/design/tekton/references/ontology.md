# Tekton ontology — the typed architecture-intent graph (v0.2)

One graph. Nodes are typed; edges are typed; **views are filters over the graph**, not
separate diagrams. Cross-tier traceability (`tekton query`) falls out because it's all one
graph. v0.2 adds the four review-driven upgrades: containment, lifecycle, qualities, and
machine-checked fitness functions.

## Node types

| type | tier it anchors | use for |
|------|-----------------|---------|
| `actor` | journey | a person / persona / external initiator |
| `journey` | journey | a user journey or flow (contain steps via `parent`) |
| `step` | journey | a step within a journey |
| `component` / `service` | system | a logical component / module / service |
| `datastore` | data | a database, queue, cache, file store |
| `entity` | data | a data entity / model / table / type |
| `infra` | infra | a host, container, cloud resource, env |
| `external` | system | a 3rd-party / external system |
| `decision` | decisions | an ADR (full Nygard fields — see below) |
| `boundary` | any | **v0.2** — bounded context / team / trust boundary; a container |
| `quality` | qualities | **v0.2** — quality attribute / NFR / constraint |

## Node fields (all optional except id/type)

```yaml
- id: api
  type: component
  label: API
  parent: engine          # v0.2 — containment; renders as nested group, collapsible
  status: current         # v0.2 — current | target | deprecated (target = dashed)
  layer: interface        # v0.2 — used by layer-order lint rules
  note: free text shown in the detail panel
```

## Edge types

`uses` · `calls` · `emits` · `consumes` · `reads` · `writes` · `stores` · `owns` ·
`deploys-to` · `runs-on` · `step-of` · `next` · `touches` · `governs` · `decides` ·
`depends-on` · `realizes` · **`constrains`** (quality→element, v0.2) ·
**`supersedes`** (decision→decision, v0.2)

Direction is semantic and matters for `query` and `lint`.

## Decisions block (Nygard ADR, v0.2)

```yaml
decisions:
  - id: adr_renderer
    label: Custom elkjs + Broomva DS renderer
    status: accepted            # proposed | accepted | superseded | deprecated
    context: why the decision was needed (the forces)
    consequences: what it costs and buys
    supersedes: adr_mermaid     # → supersedes edge
    governs: [viewer]           # → governs edges
```

## Qualities block (NFRs, v0.2)

```yaml
qualities:
  - id: q_layout_speed
    label: Layout stays interactive
    kind: performance           # performance | availability | security | portability | evolvability | ...
    target: elk layout < 1.5s at 100 nodes
    applies_to: [projector]     # → constrains edges
```

Qualities surface in the constrained node's detail panel and in the `qualities` view.

## Fitness functions — `rules:` block (v0.2)

Machine-checked design rules. `tekton lint` runs referential validation + all rules;
exit 1 on any violation (CI-gateable).

```yaml
rules:
  - id: viewer-readonly
    rule: forbid-dep            # forbid matching edges
    from: { id: viewer }        # matchers: id | type | layer
    to:   { id: model_store }
    via: [writes]               # optional; default = all edge types
    why: the viewer is a projection surface
  - id: engine-acyclic
    rule: no-cycle              # cycle detection over the via-subgraph
    via: [calls, uses, depends-on]
  - id: clean-layering
    rule: layer-order           # deps must flow in listed order
    layers: [interface, domain, data]
    via: [calls, reads, writes, uses]
```

Lint also warns (non-fatal) on orphan nodes and decisions without status.

## Views (each = node-type filter + edge-type filter)

| view | shows |
|------|-------|
| `system` | components, stores, externals, boundaries + calls/uses/reads/writes |
| `journey` | actors, journeys, steps + next/touches (steps contained via parent) |
| `data` | entities, stores, components + stores/reads/writes/owns |
| `infra` | components, infra, stores + deploys-to/runs-on |
| `decisions` | ADRs + governs/supersedes, pinned to what they govern |
| `qualities` | **v0.2** — NFRs + the elements they constrain |

Containment renders in any view where both parent and child are visible; a parent whose
type isn't in the view leaves the child free-floating (no hidden coupling).

## Design invariants (why it's built this way)

- **YAML is canonical.** Diagram and HTML are renders, never the source.
- **Layout is derived, never stored.** The model stores meaning, not positions.
- **Views are queries.** Adding a tier = types + a filter, not a new file to sync.
- **Lint is the design loop's independent verifier (h⟂U).** A model nothing checks is
  open-loop documentation; the rules block closes the loop.
- **Round-trip is git (v1).** CRDT (loro) co-editing is v2.
