# Haima Architecture

## System Design

Haima occupies the **financial layer** in the Agent OS hierarchy — between
the kernel contract (aios-protocol) and the application runtime (Arcan).

```
┌─────────────────────────────────────────────────┐
│ External World                                   │
│   HTTP APIs, Agent Services, Data Providers      │
│   ──── x402 protocol boundary (HTTP 402) ────    │
├─────────────────────────────────────────────────┤
│ Haima (Financial Layer)                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ x402     │  │ Wallet   │  │ Payment     │  │
│   │ Client   │  │ Backend  │  │ Policy      │  │
│   │ Server   │  │ (Local/  │  │ (Auto/Appr/ │  │
│   │ Middleware│  │  MPC)    │  │  Deny)      │  │
│   └────┬─────┘  └────┬─────┘  └──────┬──────┘  │
│        │              │               │          │
│   ┌────┴──────────────┴───────────────┴──────┐  │
│   │ Finance Event Publisher (→ Lago)          │  │
│   │ Financial State Projection (← Lago)       │  │
│   └──────────────────────────────────────────┘  │
├─────────────────────────────────────────────────┤
│ Agent OS Infrastructure                          │
│   ┌──────────┐  ┌──────────┐  ┌──────────────┐  │
│   │ Arcan    │  │ Autonomic│  │ Lago         │  │
│   │ (Runtime)│  │ (Homeo-  │  │ (Persistence)│  │
│   │          │  │  stasis) │  │              │  │
│   └──────────┘  └──────────┘  └──────────────┘  │
├─────────────────────────────────────────────────┤
│ aiOS Protocol (Canonical Contract)               │
│   PaymentPort | EventStorePort | PolicyGatePort  │
└─────────────────────────────────────────────────┘
```

## Data Flow

### Outgoing Payment (Agent pays for resource)

```
1. Arcan tool execution → HTTP request → 402 response
2. arcan-haima bridge → parse PAYMENT-REQUIRED header
3. Haima x402 client → PaymentRequest
4. Consult Autonomic → GET /gating/{session_id} → EconomicMode
5. PaymentPolicy.evaluate(amount) → AutoApproved | RequiresApproval | Denied
6. If RequiresApproval → ApprovalPort.enqueue() → wait for human
7. WalletBackend.sign_transfer_authorization() → EIP-3009 signature
8. Retry HTTP request + PAYMENT-SIGNATURE header
9. Facilitator.verify() → on-chain settlement → tx_hash
10. Lago.append(finance.payment_settled) → event persisted
11. Autonomic subscriber → EconomicState.balance updated
```

### Incoming Revenue (Client pays agent for task)

```
1. Agent completes task → Lago.append(finance.task_billed)
2. Client requests result → x402 server middleware → 402 + PAYMENT-REQUIRED
3. Client signs and retries with payment
4. Facilitator.verify() → on-chain settlement
5. Lago.append(finance.revenue_received) → balance increases
6. FinancialState.pending_bills → task removed
7. Autonomic → balance_to_burn_ratio improves → mode may upgrade
```

## Event Schema

All events use `EventKind::Custom` with `"finance."` namespace prefix.
This ensures forward compatibility through Lago's event journal.

Events are serialized as JSON in the `data` field of `EventKind::Custom`:

```json
{
  "event_type": "finance.payment_settled",
  "data": {
    "kind": "payment_settled",
    "tx_hash": "0xabc123...",
    "amount_micro_credits": 10000,
    "chain": "eip155:8453",
    "latency_ms": 1200,
    "facilitator": "coinbase-cdp"
  }
}
```

## Projection Model

`FinancialState` is computed by folding over all `finance.*` events:

```rust
let state = events
    .iter()
    .fold(FinancialState::default(), |mut state, event| {
        state.apply(&event.kind, event.timestamp);
        state
    });
```

This deterministic fold can be replayed from any point in the journal,
ensuring the financial state is always derivable from events.
