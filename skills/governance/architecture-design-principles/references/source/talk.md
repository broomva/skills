# Source: Talk Attribution and Chapter Map

## Attribution

- **Title**: "I was laid off by Atlassian"
- **Speaker**: Vasilios Syrakis
- **Date**: 2026-05-10
- **Duration**: 40:05
- **URL**: https://www.youtube.com/watch?v=55pTFVoclvE
- **Format**: First-person retrospective, screen-shared Excalidraw whiteboard
- **Speaker's history**: ~8 years at Atlassian (2017-2025), platform engineer
  on the edge / load-balancing team. Built and open-sourced *Sovereign*
  (an Envoy xDS management server in Python/FastAPI).

## Why this is worth distilling

The talk is unusual in three ways:

1. **Chronological build-up.** The speaker shows what was built *in the
   order it was built*, including the wrong turns (Connection library →
   Flask → FastAPI). Most architecture content shows the final state and
   omits the sequence.
2. **Specific tools named.** Envoy, Hashicorp Packer, SaltStack,
   CloudFormation, FastAPI, DynamoDB, SQS, CloudFront, Route53, ACM,
   Connection (Python lib), Sovereign (open-sourced). This anchors the
   patterns to real implementations.
3. **Non-technical postscript.** The last 8 minutes cover diplomacy,
   mentoring, conflict, and the curse-of-knowledge. Most architecture
   talks omit this; this one centers it.

## Chapter map (from YouTube)

| Time | Chapter | What it teaches |
|------|---------|-----------------|
| 00:00 | Intro | Context: 8 years at Atlassian, laid off, video as retrospective |
| 00:58 | Interview process | The whitepaper-reading exercise, troubleshooting + values, the "12 months from now" question |
| 04:16 | Starting at Atlassian | "Drinking from the firehose" — joining onboarding pattern |
| 04:35 | Building an Open Service Broker | OSB spec, FastAPI + Connection → pure Flask → FastAPI migration |
| 07:43 | Diagram of OSB architecture | FastAPI → SQS → Worker → DynamoDB; client polls; provisioning task does Route53/CloudFront |
| 09:56 | Picking a proxy technology — Envoy | Replacing enterprise LB with open-source cloud-native commodity proxy |
| 11:36 | Envoy xDS Control Plane | "Sovereign" — Templates + Context → Clusters/Routes/Listeners served via xDS |
| 14:33 | AWS Infrastructure | CloudFormation: VPC, Subnet, IGW, SG, ASG, NLB, IAM, Route53, KeyPair, ACM |
| 17:45 | Creating the machine image (AMI) | Packer + SaltStack (similar to Puppet/Ansible/Chef), provisioning steps |
| 20:22 | 24-month recap | 2000 proxies × 13 regions, long-lived infra + dynamic config + pre-provisioned |
| 21:09 | What did I do after building | Migration phase, forcing the org onto the new platform |
| 22:45 | Extending the load balancing platform | Envoy's vast config surface (virtual hosts, routes, clusters, listeners) |
| 24:37 | Envoy extensions | Network filters, HCM, external processing/authorization |
| 25:54 | Edge Compute and centralized logic | Solving cross-cutting concerns at the proxy instead of N backend services |
| 27:12 | Handling concerns for dev teams | Auth/authz/rate-limit/DDoS/logs at the edge |
| 31:35 | Diplomacy and conflict resolution | Different managers/colleagues, personality conflicts |
| 32:14 | Maintaining software over long-term | Churn as smell, onboarding-as-recurring, build ≠ maintain |
| 35:42 | Personality Conflicts | Self-awareness, anticipating conflicts |
| 37:11 | Mentoring | Distinct from teaching; the balance problem |

## The reference diagram

The complete architecture appears in the talk around 21:30 (see
[../diagrams/01-full-architecture.jpg](../diagrams/01-full-architecture.jpg)).

Reconstruction in ASCII appears in [SKILL.md](../../SKILL.md#the-reference-architecture-from-the-talk).

Components on the whiteboard:
- **Open Service Broker** cluster: FastAPI → SQS → Worker → DynamoDB; worker
  also creates Route53/CloudFront/API-calls (the "Provisioning Task")
- **Sovereign** cluster (xDS control plane): FastAPI, Configuration block
  (Context, Templates → Clusters, Routes, Listeners), reads from S3 bucket
- **EC2** cluster: Envoy proxies (annotated "2000 proxies, 13 regions")
- **AWS CloudFormation Template** cluster: Parameters, VPC, Subnet, IGW,
  SecurityGroup, AutoscalingGroup, NLB, IAM Role, Route53, KeyPair, ACM,
  feeding AMI
- **Hashicorp Packer + SaltStack Configuration** for AMI building

## Open source artifact

**Sovereign** — Envoy xDS management server, Python/FastAPI. Vasilios
mentions: "I open sourced this software and I called it Sovereign. You
can actually go find that on Bitbucket. It's a public repo at least for
now. I don't know if that's going to be the case always."

The design pattern is more durable than the specific repo. Modern
equivalents:
- **Istio Pilot** (Go) — Kubernetes-native xDS server
- **Solo.io Gloo** (Go) — Envoy-based API gateway with control plane
- **Envoy Gateway** (Go) — official Envoy project

## Stack summary

| Layer | Tech (as built at Atlassian) | Modern equivalents |
|-------|------------------------------|---------------------|
| API framework | FastAPI (Python) | FastAPI, Axum (Rust), Fastify (Node) |
| Queue | AWS SQS | SQS, Kafka, NATS, RabbitMQ |
| State | DynamoDB | DynamoDB, Postgres, FoundationDB |
| Image build | Hashicorp Packer + SaltStack | Packer + Ansible, Dockerfile, Bazel |
| Infrastructure as code | AWS CloudFormation | CloudFormation, Terraform, Pulumi, CDK |
| Proxy / data plane | Envoy | Envoy, NGINX, HAProxy, Caddy |
| Control plane | Sovereign (custom, Python) | Istio, Linkerd, Consul, custom |
| CDN | CloudFront | CloudFront, Cloudflare, Fastly |
| Sidecars | Rust (auth), various (authz, rate-limit) | Any language with gRPC server |

## How to cite this skill

When this skill informs a design decision or recommendation, cite as:

> Architecture & design principles distilled from V. Syrakis, "I was laid
> off by Atlassian" (https://www.youtube.com/watch?v=55pTFVoclvE, 2026-05-10),
> see `~/.agents/skills/architecture-design-principles/`.
