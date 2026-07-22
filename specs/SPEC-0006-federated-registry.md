# SPEC-0006: Federated Registry

> **Status:** Design Draft v0.1 — Phase 4 (placeholder in Phase 0/1)
> **Scope:** Defines how multiple Intent OS registries discover, synchronise, and trust each other
> **Editor:** Software Architect — Intent OS Project

---

## 1. Purpose

The Federated Registry spec defines how **independent Intent OS registries can discover each other, share capability manifests, and establish trust relationships**. It answers one question:

> **How does a capability published on one Intent OS instance become available on another?**

### 1.1 Why Federation, Not Centralisation

A centralised marketplace (Phase 1 goal) is useful for discoverability, but it creates a single point of control. Federation enables:

- **Private registries**: enterprises keep capabilities internal, selectively share with partners
- **Air-gapped deployments**: registries that never touch the public internet
- **Community registries**: open instances that peer with each other organically
- **Gradual adoption**: two instances can start peering without waiting for a central authority

---

## 2. Design Principles

### P1: Registries Are Autonomous

Each registry owns its data. Federation is opt-in — a registry decides which other registries to trust, what to share, and what to consume. No registry can push data to another without authorisation.

### P2: Discover, Don't Centralise

There is no "master registry." Discovery happens through peering — one registry knows about another and can query it. Metadata about peer registries is itself a capability that can be registered.

### P3: Trust Is Explicit

Trust is not transitive by default. If Registry A trusts B and B trusts C, A does NOT automatically trust C. This prevents trust-propagation attacks. Explicit transitive trust can be configured.

### P4: Content-Addressable Manifests

Every Capability Manifest is identified by its content hash (digest field from SPEC-0001). This allows deduplication and integrity verification across registries without requiring a shared naming authority.

---

## 3. Architecture

### 3.1 Registry Identity

Each registry has a unique identity:

```yaml
registry_identity:
  registry_id: uuid                 # Globally unique, generated at first init
  display_name: string              # Human-readable name
  description: string | null
  public_key: string                # Ed25519 public key for signature verification
  endpoints:
    query: URL                      # Where to send registry queries
    sync: URL | null                # Where to send sync requests (optional)
  version: string                   # Intent OS version
  capabilities_count: integer       # Self-reported count
  last_seen: ISO8601 | null         # When this registry was last reachable
```

### 3.2 Peer Discovery

A registry discovers peers through:

1. **Static configuration**: admin manually adds a peer URL
2. **Well-known endpoint**: registry exposes `/.well-known/intent-os-registry.json`
3. **Peer introduction**: an existing peer introduces a new one
4. **Registry-of-registries**: an optional "meta-registry" that lists known registries (Phase 4+)

```bash
# CLI: add a peer
intent-os registry peer add https://registry.example.com

# CLI: list known peers
intent-os registry peer list

# CLI: query a peer for capabilities
intent-os registry peer query https://registry.example.com "text summarization"
```

### 3.3 Query Flow

```
Registry A wants to find a capability on Registry B:

1. A sends a signed query to B's query endpoint:
   {
     "query": "text summarization",
     "limit": 10,
     "min_score": 0.5,
     "requester_registry": "uuid-of-A",
     "requester_signature": "...",
     "timestamp": ISO8601
   }

2. B authenticates the request (verifies A's public key)
3. B searches its local registry using its semantic search engine
4. B returns results, each including the manifest's digest and a signature:
   {
     "results": [{
       "capability": {name, version, digest, description, tags},
       "manifest_url": "intent-os://registry-b.example.com/manifests/{digest}",
       "signature": "..."  # B's signature over the capability summary
     }],
     "registry_signature": "..."  # B's signature over the entire response
   }

5. A can now fetch the manifest by digest
6. Before executing, A verifies the manifest digest matches
```

### 3.4 Manifest Retrieval

Manifests are fetched by content hash, never by name (names can collide):

```bash
# Fetch a manifest by digest
intentos registry fetch --from https://registry-b.example.com \
  --digest sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855

# Import into local registry
intent-os registry register fetched_manifest.yaml --publisher "peer:registry-b"
```

### 3.5 Synchronisation (Phase 4+)

For bulk synchronisation between trusted peers:

```yaml
sync_request:
  requester_registry: uuid
  requester_signature: "..."
  timestamp: ISO8601
  since: ISO8601              # Only return capabilities updated after this time
  limit: 1000                 # Maximum number of capabilities to return
  offset: 0                   # Pagination offset
```

The response contains a batch of capability summaries with digests. The requester then fetches only the manifests it doesn't already have (by comparing digests).

---

## 4. Trust Model

### 4.1 Trust Levels

| Level | Meaning | Use Case |
|---|---|---|
| `none` | Don't accept anything from this peer | Blocked registries |
| `query` | Accept query results but verify each manifest | Public community registries |
| `sync` | Accept bulk syncs from this peer | Trusted partner registries |
| `mirror` | Automatically trust everything from this peer | Owned secondary registries |

### 4.2 Trust Configuration

```yaml
# Local registry config (~/.intent-os/registry_config.yaml)
peers:
  - registry_id: "abc-123"
    display_name: "Community Registry"
    public_key: "MCowBQYDK2VwAyEA..."
    trust_level: query
    endpoints:
      query: "https://community.intent-os.org/query"
    last_synced: null

  - registry_id: "def-456"
    display_name: "Enterprise Hub"
    public_key: "MCowBQYDK2VwAyEA..."
    trust_level: sync
    endpoints:
      query: "https://hub.example.com/query"
      sync: "https://hub.example.com/sync"
    last_synced: "2026-07-22T10:00:00Z"

default_trust_level: query
```

### 4.3 Signature Verification

Every cross-registry message is signed with the sending registry's private key. The receiving registry verifies against the stored public key for that peer. Key rotation is handled by re-registering the peer with a new key.

```
Message signing:
  message_bytes = canonical_json(message_without_signature)
  signature = ed25519.sign(private_key, message_bytes)

Verification:
  is_valid = ed25519.verify(public_key, message_bytes, received_signature)
```

---

## 5. CLI Interface

```bash
# Peer management
intent-os registry peer add <url> [--trust-level query|sync|mirror]
intent-os registry peer remove <registry-id>
intent-os registry peer list
intent-os registry peer trust <registry-id> --level query

# Cross-registry query
intent-os registry search <query> --include-peers
intent-os registry fetch <digest> --from <registry-id>

# Registry identity
intent-os registry status           # Shows local registry identity and peer count
intent-os registry export-identity  # Export registry identity for sharing
```

---

## 6. Security Considerations

### 6.1 Threat Model

| Threat | Impact | Mitigation |
|---|---|---|
| Impersonation: fake registry pretends to be another | Low — manifests are verified by digest | Public key verification, digest integrity |
| Malicious manifest injection via peer | Medium — attacker publishes harmful manifest | Trust levels restrict sync sources; manifests are verified before execution via SecurityManager |
| Replay attack: old sync data replayed | Low — data is content-addressed, duplicates are harmless | Timestamp in every request; registries reject requests with timestamps older than 5 minutes |
| Denial of service: excessive queries from peer | Medium | Rate limiting per peer; configurable query budget |

### 6.2 Privacy

- Registry queries are logged server-side (like any search)
- A registry can refuse to serve certain capabilities to specific peers
- Capability content (the manifest itself) is not encrypted — deploy over HTTPS for transport security
- Capability execution data (Event Records) is never shared across registries unless explicitly exported

---

## 7. Relationship with Existing Systems

| System | Relationship |
|---|---|
| **CapabilityRegistry (SPEC-0001)** | The local database — federated queries are an extension of the existing `find_by_text()` API |
| **Event Schema (SPEC-0003)** | Events stay local by default; federated sync does NOT include execution records |
| **Security Manager (SPEC-0004)** | Trust levels are evaluated as policies — a fetched manifest's trust level becomes part of its security context |
| **Capability Manifest (SPEC-0001)** | The digest field (already defined) becomes the primary identifier for cross-registry manifest retrieval |

---

## 8. Phase Transition Plan

### Phase 4 — Foundation (can start now)

- [x] This design document
- [ ] `intent-os registry peer` CLI subcommands
- [ ] Peer identity generation (key pair on first init)
- [ ] Trust configuration file support

### Phase 4 — Query

- [ ] Query endpoint on MCP server or dedicated HTTP handler
- [ ] Signature generation and verification
- [ ] Cross-registry semantic search

### Phase 4+ — Sync

- [ ] Bulk sync protocol
- [ ] Incremental sync (since timestamp)
- [ ] Conflict resolution (same digest → same manifest; different digest → different version)
- [ ] User-facing UX for browsing peer capabilities

---

## 9. Validation Rules

1. **Digest uniqueness**: A manifest's digest (sha256 of its YAML content) must be unique within a registry's scope. Two manifests with the same digest are considered identical.
2. **Signature freshness**: Cross-registry messages must include a timestamp within 5 minutes of the receiver's clock.
3. **Trust non-transitivity**: Registry A trusting B and B trusting C does NOT imply A trusts C. Trust must be explicitly configured.
4. **Peer identity**: A registry's identity key pair must be generated at first init and persisted. Loss of the private key requires manual peer re-registration.
5. **Rate limiting**: A registry must enforce per-peer query rate limits (default: 100 queries/minute).

---

## 10. References

- SPEC-0001: Capability Manifest — digest field, publisher identity
- SPEC-0004: Security Model — trust verification patterns
- Fediverse (ActivityPub) — federation patterns: autonomous instances, opt-in peering
- Docker Registry API — content-addressable image retrieval via digest
- Keybase — public key identity model for distributed trust
