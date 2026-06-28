# Edge Compute & Sidecars: Centralizing Cross-Cutting Concerns

## The core insight

> "If we can deal with the problems here [at the edge] before they reach a
> service, we save a lot of time, we save some money, and it saves the
> customer time. It's great for everyone, really."

Every cross-cutting concern solved at the edge is a concern *not* solved by
1000 backend teams. The savings compound multiplicatively, not additively.

## The cross-cutting concerns (in order of value-per-effort)

| Concern | Native to proxy? | Why edge | Cost if per-service |
|---------|------------------|----------|---------------------|
| **DDoS protection** | No (use CDN like CloudFront) | Drops traffic before it reaches your network | Every team writes rate-limiting that doesn't scale |
| **TLS termination** | Yes (Envoy SDS) | Cert rotation in one place | Cert renewal incidents per team |
| **Authentication** | Sidecar (ext_authz) | Same auth for 1000 services | OAuth re-implementations, security holes |
| **Authorization** | Sidecar (ext_authz) | Policy-as-data, centrally managed | Inconsistent permissions, audit nightmares |
| **Rate limiting** | Native (with sidecar for global) | Protects backends from abuse + retries | Cache invalidation storms, retry hell |
| **Access logs** | Native (Envoy) | One log shape, one pipeline | Schema drift, partial coverage |
| **Tracing / metrics** | Native (Envoy) | Standardized telemetry | Each team picks a vendor, no joins |
| **Routing / canary / blue-green** | Native (Envoy) | Single source of truth for traffic shape | Deploy tooling per team |

## Native vs Sidecar — when to choose which

```
                          ┌─────────────────────┐
                          │                     │
                          │  Is the concern     │
                          │  implementable as   │
                          │  Envoy filter /     │
                          │  built-in config?   │
                          │                     │
                          └──────────┬──────────┘
                                     │
                       Yes ──────────┼────────── No
                        │                         │
                        ▼                         ▼
            ┌─────────────────────┐   ┌─────────────────────┐
            │ Native (Envoy)      │   │ Sidecar             │
            │ • Lowest latency    │   │ • Own language      │
            │ • No extra hops     │   │ • Own deploy lifecycle│
            │ • Hard to extend    │   │ • Owned by other    │
            │                     │   │   team possibly     │
            │ Use for: logging,   │   │                     │
            │   routing, headers, │   │ Use for: auth,      │
            │   basic rate limit  │   │   authz, rate-limit │
            │                     │   │   with global state │
            └─────────────────────┘   └─────────────────────┘
```

**At Atlassian**: access logs lived natively in Envoy (network filter +
HCM access_log config). Authentication was a Rust sidecar (written by
Vasilios). Authorization and rate-limiting were sidecars contributed by
other teams. All sidecars were baked into the AMI by the Packer/SaltStack
flow.

**The "ext_authz" filter** is the key Envoy primitive that makes sidecars
work: a single filter that calls an external gRPC/HTTP service per request,
which can deny or allow. The sidecar runs as a separate process on the
same host (localhost, low latency).

## The multi-team contribution model

The hidden benefit of the sidecar pattern: **other teams can own and ship
their own sidecars without forking the proxy**.

```
                Platform team owns:
                  • Envoy itself
                  • Sovereign xDS control plane
                  • AMI build pipeline
                  • Native filter configuration

                Other teams contribute:
                  • Authentication sidecar (Vasilios/security team, Rust)
                  • Authorization sidecar (authz team)
                  • Rate-limiting sidecar (reliability team)

                AMI bakes in all sidecars at image-build time.
                Each sidecar has its own deploy lifecycle, language,
                and code review process.
```

**Why this scales the platform team**: without sidecars, every new
cross-cutting concern requires a PR to the platform team. With sidecars,
the platform team owns the *contract* (how sidecars are baked, configured,
talked to via ext_authz) and other teams own the *implementations*.

**Anti-pattern**: forcing all cross-cutting logic into proxy filters.
You'll either rewrite the proxy or get a 10,000-line config file.

## The architectural rule

> The further left (closer to the client) a concern is solved, the cheaper
> it gets per backend service.

```
   client ──▶ CDN ──▶ NLB ──▶ Proxy + sidecars ──▶ backends
                 ▲        ▲          ▲
                 │        │          │
                 │        │          └─ auth, authz, rate-limit, headers
                 │        └──────────── TLS, basic flow control
                 └───────────────────── DDoS, geo-routing, caching
```

If your team is asking "should we put X in the API gateway or in each
service?", the answer is almost always **gateway**, *if* X is needed by more
than 2 services. The maintenance cost of N implementations grows
super-linearly in N.

## Tradeoffs and exceptions

**When *not* to centralize at the edge**:

1. **Concerns specific to one team / one product**. Don't push product
   logic into the proxy.
2. **High variability per service**. If the auth model is genuinely
   different per service (some use OAuth, some use mTLS, some use API
   keys), centralization adds branching complexity. Picking one auth
   model org-wide is the real fix.
3. **Performance-sensitive paths**. ext_authz adds a localhost round-trip
   (~0.1-1ms). For 99% of services that's invisible; for a high-frequency
   trading service it's not.
4. **Concerns the platform team can't operate at the edge's reliability
   level**. If your sidecar dies, all traffic through that proxy dies.
   The sidecar's SLO must match the proxy's SLO.

## The cost of centralization

The flip side is real and worth naming:

- **Backend teams lose autonomy**: they can't pick their own auth scheme.
- **The platform team becomes the bottleneck**: every new cross-cutting
  concern requires platform-team review.
- **Outages have larger blast radius**: an Envoy bug downs everyone, not
  one team.

The talk's implicit answer: these costs are worth paying for an org with
~1000 services. They are *not* worth paying for an org with ~5. The
breakeven is somewhere around 20-50 services with sufficient overlap in
concerns.

## Putting it together (the edge call path)

```
Customer request
   ↓
CloudFront (DDoS, geo, caching)
   ↓
NLB (L4, TLS passthrough)
   ↓
Envoy (TLS terminate, route lookup, header munging, access log)
   │
   ├─→ ext_authz call → Authentication sidecar (Rust)
   │                       returns identity claims
   ├─→ ext_authz call → Authorization sidecar
   │                       checks policy, allow/deny
   ├─→ HCM filter   → Rate limit sidecar (with global counters)
   │
   ↓ (if all allow)
Backend service
   ↑ response
   ↓ (back through Envoy, access log records duration + status)
NLB → CloudFront → Customer
```

Backend service sees: an authenticated request with identity headers
already populated, never sees a denied request, never sees a rate-limited
request. The backend team writes business logic only.
