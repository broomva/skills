# Haima Regulatory Compliance Reference

**Date**: 2026-03-23 | **Source**: BRO-43 analysis

## Regulatory Position

Haima is a **technology layer** — not a money transmitter. All fund movement flows through
licensed partners (Coinbase CDP, Circle). This is the foundational compliance principle.

## Partner Licensing Coverage

| Partner | Licenses | Role |
|---|---|---|
| Coinbase CDP | FinCEN MSB + 48 state MTLs + NY BitLicense | x402 facilitator, on-chain settlement |
| Circle | EU EMI (MiCA), OCC national trust bank (conditional) | USDC issuer, fiat on/off ramp |
| Stripe/Bridge | 50 US states + EU + 40+ countries, OCC trust charter | MPP (Phase F6), fiat hybrid |

## Key Compliance Dates

| Date | Event | Impact |
|---|---|---|
| Apr 2, 2026 | NIST Identity/Auth comment period closes | Submit comments |
| Aug 2, 2026 | EU AI Act full enforcement | High-risk AI system compliance required |
| Dec 9, 2026 | EU Product Liability Directive transposition | Software = product, strict liability |
| ~2027 | PSD3/PSR enforcement | TSP exemption confirmation |

## Architecture Constraints

1. **No custody**: Haima never holds, controls, or has constructive possession of any value
2. **No transmission**: All fund movement through Coinbase CDP (licensed)
3. **No account management**: Agent wallets are self-custodied (secp256k1)
4. **Fail-closed**: Payment system denies on error, never approves
5. **Immutable audit**: Lago event journal records every financial decision

## EU AI Act Compliance (Haima Advantages)

| Requirement | Haima Feature |
|---|---|
| Art. 12 Logging | Lago immutable event journal |
| Art. 14 Human Oversight | PaymentPolicy approval tiers + session caps |
| Art. 13 Transparency | Open-source + documented decision logic |
| Art. 15 Robustness | Fail-closed design, key zeroization |

## KYA (Know Your Agent) Model

Traditional KYC maps to agent identity:
- **Identity**: secp256k1 wallet public key
- **Delegation**: Agent wallet -> master key -> KYC'd human (via Coinbase)
- **Authorization**: PaymentPolicy (session caps, auto-approve thresholds)
- **Monitoring**: Lago event journal + Autonomic economic mode governance
