# Key Frames from the Talk

Eight key frames extracted from the talk at decision-illustrating moments.
Each is a JPEG screenshot of the speaker's Excalidraw whiteboard at a
specific timestamp.

| File | Timestamp | What's shown |
|------|-----------|--------------|
| `01-full-architecture.jpg` | 21:30 | **The complete reference architecture.** Open Service Broker (FastAPI→SQS→Worker→DynamoDB) on top, Sovereign xDS control plane (Templates + Context → Clusters/Routes/Listeners) bottom-left, EC2 Envoy fleet (2000 proxies × 13 regions) center, AWS CloudFormation cluster (Parameters/VPC/Subnet/IGW/SG/ASG/NLB/IAM/Route53/ACM/KeyPair) right, Packer + SaltStack at bottom for AMI building. **Single most important frame in the talk.** |
| `02-osb-fastapi.jpg` | 08:00 | Open Service Broker starts as one FastAPI box. The minimal starting point. |
| `03-osb-async-task.jpg` | 10:00 | OSB extended: FastAPI → SQS → Worker → DynamoDB, worker creates Route53/CloudFront/API calls asynchronously. The async task orchestration pattern. |
| `04-sovereign-xds.jpg` | 12:00 | Sovereign control plane: Context, Templates → Clusters, Routes, Listeners, exposed via xDS to Envoy. The template+context separation pattern. |
| `05-aws-cfn.jpg` | 15:00 | AWS CloudFormation infrastructure: Envoy fleet (2000 proxies, 13 regions) provisioned via CFN with IAM Role, Route53, KeyPair, ACM, etc., feeding into AMI. |
| `06-ami-packer-saltstack.jpg` | 18:00 | AMI build pipeline: Hashicorp Packer + SaltStack configuration produces the standard AMI that all proxies share. The image-layer IaC. |
| `07-edge-concerns.jpg` | 28:00 | Cross-cutting concerns at the edge: Customer → Envoy → Backend, with DDoS protection, Authentication, Authorization, Rate Limiting, Access logs listed beside the Envoy node. |
| `08-sidecars.jpg` | 30:00 | The full edge-compute architecture: CloudFront (DDoS) → NLB → Envoy (access logs native) → Sidecars (Authentication, Authorization, Rate Limiting) → Backend Service. The sidecar pattern for what the proxy can't do natively. |

## Reading the diagrams

The whiteboard uses Excalidraw conventions:
- **Rounded rectangles** = services / components
- **Circles** = proxies (Envoy specifically)
- **Arrows** = data flow direction
- **Cluster boxes** = grouping (Open Service Broker, Sovereign, EC2,
  AWS CloudFormation Template are all cluster names)
- **Text annotations** = labels and counts (e.g., "2000 proxies, 13 regions")

## ASCII reconstruction

For an ASCII version that can be copy-pasted into specs/docs, see the
"Reference Architecture" section in [../../SKILL.md](../../SKILL.md).
