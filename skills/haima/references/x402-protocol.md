# x402 Protocol Reference

## Overview

x402 is an open, internet-native payment protocol that activates HTTP's dormant
`402 Payment Required` status code. Created by Coinbase (May 2025), co-governed
by the x402 Foundation (Coinbase, Cloudflare, Visa, Google).

**Specification**: [github.com/coinbase/x402](https://github.com/coinbase/x402)
**Rust crate**: [x402-rs](https://crates.io/crates/x402-rs) (v0.12.5, Apache 2.0)

## HTTP Headers

| Header | Direction | Content |
|--------|-----------|---------|
| `PAYMENT-REQUIRED` | Server → Client (402) | Base64-encoded JSON with payment terms |
| `PAYMENT-SIGNATURE` | Client → Server (retry) | Base64-encoded signed payment authorization |
| `PAYMENT-RESPONSE` | Server → Client (200) | Settlement confirmation with tx hash |

## Payment Schemes

### Exact (production)
Transfer a specific amount. The only scheme in production today.

```json
{
  "scheme": "exact",
  "network": "eip155:8453",
  "token": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
  "amount": "10000",
  "recipient": "0x...",
  "facilitator": "https://x402.org/facilitator"
}
```

### Signing (EIP-3009)

For USDC payments, x402 uses `transferWithAuthorization` (EIP-3009):
- Signer authorizes a specific transfer without on-chain gas
- Facilitator submits the authorization to execute the transfer
- No gas needed from the payer — facilitator pays gas

## Facilitator API

### POST /verify
Verify a payment payload and settle on-chain.

```json
Request:  { "payment_payload": "base64...", "payment_requirements": "base64..." }
Response: { "valid": true, "tx_hash": "0x...", "error": null }
```

### GET /supported
Query supported networks and schemes.

```json
Response: { "networks": ["eip155:8453", "eip155:84532"], "schemes": ["exact"] }
```

## Rust Integration (x402-rs)

### Server (axum middleware)
```rust
use x402_axum::X402Middleware;

let x402 = X402Middleware::new("http://facilitator.example.com");
let app = Router::new().route(
    "/paid-content",
    get(handler).layer(x402.with_price_tag(...))
);
```

### Client (reqwest)
```rust
use x402_reqwest::{X402Client, PaymentsExt};

let signer: Arc<PrivateKeySigner> = Arc::new("0x...".parse()?);
let x402_client = X402Client::new().register(V2Eip155ExactClient::new(signer));
let client = Client::new().with_payments(x402_client).build();
let res = client.get("https://example.com/protected").send().await?;
```

## Chain Identifiers (CAIP-2)

| Chain | CAIP-2 ID | USDC Contract |
|-------|-----------|--------------|
| Base | eip155:8453 | 0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913 |
| Base Sepolia | eip155:84532 | 0x036CbD53842c5426634e7929541eC2318f3dCF7e |
| Ethereum | eip155:1 | 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 |

## Comparison: x402 vs MPP (Stripe)

| | x402 | MPP (Stripe/Tempo) |
|---|---|---|
| Settlement | Per-network (~200ms-2s) | Tempo sub-second |
| Payment methods | Stablecoins only | Stablecoins + fiat (via SPTs) |
| Sessions | Per-request (V2 adds sessions) | First-class streaming |
| Compliance | Merchant-managed | Full stack included |
| Best for | Permissionless, indie APIs | Enterprise with compliance needs |

Haima supports x402 natively (Phase F0-F4) and MPP via future adaptation (Phase F6).
