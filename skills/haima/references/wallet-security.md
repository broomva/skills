# Wallet Security

## Key Management

### Generation
- secp256k1 keypair via `k256` crate (pure Rust, no OpenSSL)
- Random number generation via `rand` crate with `OsRng` (CSPRNG)
- Ethereum-compatible address: `keccak256(uncompressed_pubkey[1..])[12..]`

### Storage
- Private key encrypted with ChaCha20-Poly1305 (AEAD)
- Encryption key derived from agent's master secret (Phase F2)
- Encrypted blob stored in Lago content-addressed store (SHA-256 + zstd)
- Blob ID stored in `EconomicIdentity.key_blob_id`

### In-Memory Protection
- Private key wrapped in `Zeroizing<Vec<u8>>` (zeroized on drop)
- `LocalSigner` holds `SigningKey` (zeroized by k256 internally)
- No logging of key material (enforced by code review)

### Backup & Recovery
- Lago blob store provides content-addressed immutability
- Encrypted key can be backed up via Lago's standard blob export
- Phase F2: integration with Coinbase CDP MPC for distributed key custody

## WalletBackend Trait

The `WalletBackend` trait abstracts wallet implementations:

```rust
pub trait WalletBackend: Send + Sync {
    fn address(&self) -> &WalletAddress;
    async fn sign_message(&self, message: &[u8]) -> HaimaResult<Vec<u8>>;
    async fn sign_typed_data(&self, hash: &[u8; 32]) -> HaimaResult<Vec<u8>>;
    async fn sign_transfer_authorization(...) -> HaimaResult<Vec<u8>>;
    fn backend_type(&self) -> &str;
}
```

### LocalSigner (current)
- Signs directly with in-memory private key
- Suitable for single-agent deployments
- Private key never leaves the process

### MPC Wallet (planned)
- Key shares distributed across multiple parties
- No single point of failure for key compromise
- Coinbase CDP MPC API for threshold signing
- Same `WalletBackend` interface — transparent to callers

## Payment Policy as Safety Gate

Payment authorization is never automatic without bounds:

| Policy Parameter | Default | Purpose |
|-----------------|---------|---------|
| `auto_approve_cap` | 100 μc ($0.0001) | Max auto-approve per tx |
| `hard_cap_per_tx` | 1,000,000 μc ($1.00) | Absolute max per tx |
| `session_spend_cap` | 10,000,000 μc ($10.00) | Max total per session |
| `max_tx_per_minute` | 10 | Rate limit |
| `allow_in_hibernate` | false | Block payments at zero balance |
| `allow_in_hustle` | true | Only auto-approve in low-balance mode |

These act as control-metalayer governance gates — preventing runaway
spending even if the agent loop has a bug.

## Threat Model

| Threat | Mitigation |
|--------|-----------|
| Key theft from memory | Zeroize on drop, no logging |
| Key theft from storage | ChaCha20-Poly1305 encryption |
| Runaway spending | PaymentPolicy caps + rate limits |
| Facilitator compromise | On-chain settlement is verifiable |
| Replay attacks | EIP-3009 nonces prevent replay |
| Man-in-the-middle | HTTPS + cryptographic signatures |
