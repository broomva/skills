# Self-Service Platforms: Patterns

Six patterns that the talk converged on, in the order they appeared.

## 1. The Open Service Broker (OSB) Pattern

**Shape**: a web API that brokers resource provisioning. Devs request a typed
"service instance" of a typed "plan", get back a binding (DNS, creds, etc.).

**Endpoints** (from the OSB spec):

- `GET  /v2/catalog` — list services and plans the broker can provision
- `PUT  /v2/service_instances/:id` — provision
- `PATCH /v2/service_instances/:id` — update
- `DELETE /v2/service_instances/:id` — deprovision
- `PUT  /v2/service_instances/:id/service_bindings/:bid` — bind credentials

**Why it's useful even outside K8s**: the spec is a contract for "give me a
typed resource". Whether the backing impl is K8s operators, Terraform,
CloudFormation, or a custom worker doesn't matter to the dev.

**At Atlassian**: the OSB API was a `FastAPI` app. Plans corresponded to
"load balancer with ACM cert + Route53 entry + CloudFront distribution".

**Anti-pattern**: exposing the backing tools (raw Terraform, raw kubectl)
directly to dev teams. The OSB gives you a versioned contract; the underlying
tooling is free to change underneath.

> The catalog endpoint lists all of the services and plans that are available
> on the OSB, and just metadata about them. You might query the service
> broker and then display some of the metadata in your console... where
> developers can click and provision things.

## 2. Async Task Orchestration (FastAPI → SQS → Worker → DB)

**Shape**:

```
client ─PUT─▶ FastAPI ─enqueue─▶ SQS ─dequeue─▶ Worker
   ▲             │                                 │
   │             │                                 ├─▶ Route53
   │             │                                 ├─▶ CloudFront
   │             │                                 └─▶ API calls
   │             ▼                                 │
   │          DynamoDB ◀────────────────write status
   │             ▲
   └─poll status─┘
```

**Why**: provisioning takes seconds-to-minutes. If you block the API thread
on the work, you get timeouts, retried writes (creating duplicate resources),
and partial-state nightmares.

**The client contract**: returns immediately with a task ID and "in progress"
status. Client polls until it sees `succeeded` or `failed`.

**At Atlassian**: client → FastAPI returns a 202 with a task ID. The worker
does the actual AWS API calls (which are slow and rate-limited). Status writes
to DynamoDB. Client polls FastAPI which reads DynamoDB.

**Critical detail from the talk**: "the web worker wouldn't do it itself.
It would actually send that over SQS." Resist the urge to do "just a bit"
of work on the API path.

## 3. The Three IaC Layers

Many teams collapse these into one. The talk's separation is the durable shape:

| Layer | Tool used | Cadence | Risk profile | What it owns |
|-------|-----------|---------|--------------|--------------|
| **Image** | Hashicorp Packer + SaltStack | weeks | Fleet-wide (every machine bakes a new AMI) | OS, agents, daemons, base packages, hardening |
| **Infrastructure** | AWS CloudFormation | months | Regional (one region at a time) | VPC, subnet, IGW, SG, ASG, NLB, IAM, Route53, ACM, key pair |
| **Runtime config** | Sovereign (xDS control plane) | seconds | Per-tenant | Envoy clusters, routes, listeners, filter chains |

**Why three layers, not one or two**:

- **Image** lives for weeks because AMI builds are slow and risky. You don't
  want to rebake the image to change a routing rule.
- **Infrastructure** lives for months because changing VPC/subnet/IAM is
  high-blast-radius and rarely needs to change.
- **Runtime config** lives for seconds because that's where developer
  velocity lives. Devs ship routing changes every hour; you cannot tie
  those to AMI rebuilds.

**Pattern**: the **inner layer should change the most slowly**. Inverting
this — putting business logic in the AMI — is the most common platform-team
mistake.

**Cargo-cult warning**: many teams adopt Kubernetes and *re-collapse* these
layers because the K8s control plane handles all three. Don't. The cadence
mismatch is real; you'll feel it when you need to ship a CVE patch and
realize the only path is a rolling reboot of customer pods.

## 4. The Control Plane / Data Plane Split (xDS)

**Shape**:

```
                    ┌─────────────────────┐
                    │   Control Plane     │
                    │   (Sovereign)       │
                    │                     │
                    │  reads DB + S3      │
                    │  renders templates  │
                    │  serves xDS API     │
                    └──────────┬──────────┘
                               │ gRPC / REST (xDS)
                               │ ADS (Aggregated Discovery Service)
                ┌──────────────┼──────────────┐
                ▼              ▼              ▼
            ┌───────┐      ┌───────┐      ┌───────┐
            │Envoy 1│      │Envoy 2│ ...  │EnvoyN │  (data plane)
            └───────┘      └───────┘      └───────┘
              long-lived processes, never restart for config change
```

**Why this matters**: with a control plane, **proxy lifetime is independent
of config lifetime**. You can deploy 2000 proxies once and reconfigure them
forever. Without it, every config change requires touching the proxy
process.

**The xDS API surface** (Envoy-specific but generalizable):

- **CDS** — Cluster Discovery Service (which backends exist)
- **EDS** — Endpoint Discovery Service (instances of each cluster)
- **RDS** — Route Discovery Service (HTTP routes)
- **LDS** — Listener Discovery Service (ports/filter chains)
- **SDS** — Secret Discovery Service (TLS certs)
- **ADS** — Aggregated DS (all of the above, ordered)

**At Atlassian**: Sovereign was a FastAPI app that polled DynamoDB + S3,
rendered Jinja templates into Envoy config, and served xDS. The proxies
long-polled the control plane and applied diffs.

**Generalizable beyond Envoy**: the same pattern fits any fleet-of-workers
problem — feature flags (LaunchDarkly), DNS (Route53 with health checks),
content distribution (Fastly's instant purge), Kubernetes itself (the
api-server is a control plane, kubelet is the data plane).

## 5. Template + Context Separation

**Shape**: a typed dev-facing parameter set ("Context") flows into
platform-authored logic ("Templates") to produce complex output config.

```
dev's JSON input (Context)
   │ ─ tenant_id: "growth"
   │ ─ domains: ["growth.atlassian.com"]
   │ ─ rate_limit_rps: 100
   │ ─ requires_auth: true
   ▼
Template (platform-authored Jinja/Tera)
   │ {% if requires_auth %}
   │   http_filters:
   │     - name: envoy.filters.http.ext_authz
   │       config:
   │         grpc_service: { ... }
   │ {% endif %}
   ▼
Generated Envoy config (full power, dev never sees raw config)
```

**Why this is better than letting devs write Envoy config directly**:

1. **Validation**: Context schemas are small and tractable. Raw Envoy
   config is enormous and footgun-rich.
2. **Forward compatibility**: platform team changes how `requires_auth`
   maps to filter chains; devs don't relearn anything.
3. **Cross-cutting upgrades**: a security fix becomes "patch the template";
   all tenants get it automatically on next render.

**The locus of platform team logic**: live in the templates. Every product
feature the platform offers is a clause in a template.

**Anti-pattern**: letting devs override or extend templates per-tenant.
The moment you have N templates, you have N-1 bugs.

## 6. Validate at the Boundary

**The rule**: validate Context (dev input) at the API boundary. Templates
assume valid input.

**Why**: an invalid Context that reaches the template either crashes the
render (good — caught early) or produces an *invalid Envoy config* that
makes it onto live proxies (bad — traffic loss).

```
   ┌─────────────────────────────────────────────────────────┐
   │  dev JSON                                               │
   │     │                                                   │
   │     ▼                                                   │
   │  ┌────────────────┐  ← Pydantic model, strict typing    │
   │  │ Boundary check │    type checks, ranges, regex      │
   │  │ (validate now) │    cross-field invariants          │
   │  └────────────────┘    (fail fast, refuse render)      │
   │     │                                                   │
   │     ▼                                                   │
   │  Template (assume valid)                                │
   │     │                                                   │
   │     ▼                                                   │
   │  Envoy config (assumed valid by template)               │
   └─────────────────────────────────────────────────────────┘
```

**At Atlassian**: dev input was validated at the broker (Pydantic / OpenAPI
spec). Templates were free to assume e.g. that `tenant_id` was a valid
slug because the boundary check enforced it.

**Two further defenses worth adding** (not all explicit in the talk but
implied by the model):

- **Render-time validation**: after templating, run `envoy --mode validate`
  against the generated config before serving it to the data plane.
- **Canary rollout**: push new config to 1% of proxies first, monitor for
  5xx spike, only then roll out.

## Putting it all together (the OSB → Sovereign → Envoy flow)

```
1. dev writes simple JSON to a file in version control
2. CI uploads JSON to OSB API (FastAPI)
3. OSB writes provisioning task to SQS
4. Worker picks up task, creates AWS resources (Route53, ACM, CloudFront),
   writes status to DynamoDB
5. Sovereign control plane polls DynamoDB, renders templates with the new
   context, exposes via xDS
6. Envoy proxies long-polling xDS receive the new config diff
7. Traffic starts flowing through the new routes
```

This is the complete loop. Every box in it can be (and was) scaled, replaced,
or upgraded independently because the seams between them are typed APIs,
not shared databases.
