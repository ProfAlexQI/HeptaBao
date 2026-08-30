# HeptaBao P0 Audit and Outcome Protocol V1

## 1. Scope

This contract defines the audit ordering and outcome vocabulary for `HB-P0-DEV-MEMORY`. It covers transport rejection, request dispatch, mutation outcome, response audit and response delivery. It is not a production audit-device, durability or non-repudiation claim.

## 2. Request-attempt identity

A request-attempt ID is allocated immediately after `accept` and before any request bytes are parsed. Therefore malformed framing, duplicate headers, Host mismatch, read timeout, read I/O failure and connection-capacity rejection can be correlated without storing raw secret-bearing bytes.

A valid client-proposed `X-HeptaBao-Request-Id` may replace the attempt ID after strict parsing and exact Host verification. The original attempt ID is transport-local metadata; future structured audit schemas must preserve the mapping when both identities exist.

## 3. Stable phases

The logical state machine is:

```text
CONNECTION_ACCEPTED
→ REQUEST_PARSE_ACCEPTED | REQUEST_REJECTED
→ REQUEST_AUDITED
→ DISPATCH_NOT_ATTEMPTED | DISPATCH_ATTEMPTED
→ NOT_COMMITTED | COMMITTED | OUTCOME_UNKNOWN
→ RESPONSE_AUDITED | RESPONSE_AUDIT_FAILED
→ RESPONSE_DELIVERED | RESPONSE_DELIVERY_FAILED
```

The current shared `AuditEvent` schema represents request rejection, request acceptance, prepared/committed response and post-commit audit failure. Transport-only failures use `operation=None`, `RequestRejected`, `NotAttempted` and a stable detail code. Delivery failure is recorded with a stable detail code and the known commit disposition; a future schema revision must expose delivery as a first-class phase rather than overloading a request-level phase.

## 4. Ordering invariants

1. Parse or Host rejection is audited before the error response is written.
2. If rejection audit fails, the response becomes 503 and states that rejection audit is unavailable.
3. Request audit succeeds before any state mutation.
4. Request-audit failure prevents dispatch and mutation.
5. A successful mutating operation is marked committed before response-audit evaluation.
6. Response-audit failure after commit returns 503 with `committed=true` and a recovery reference.
7. A response delivery failure does not change a committed outcome and must not trigger an automatic retry.
8. No audit event contains raw token, unseal key, secret value, signature, nonce or request body.

## 5. Stable transport detail codes

The P0 transport uses bounded identifiers including:

- `connection-capacity-exhausted`;
- `request-read-deadline-exceeded`;
- `request-read-io-failed`;
- `host-listener-mismatch`;
- `client-request-id-invalid`;
- `client-request-id-replayed`;
- `request-id-registry-unavailable`;
- `request-id-registry-saturated`;
- `protocol-duplicate-header`;
- `protocol-transfer-encoding-forbidden`;
- `protocol-content-length-mismatch`;
- `response-delivery-failed-before-commit`;
- `response-delivery-failed-after-commit`.

Unknown free-form exception text is not a stable machine identifier.

## 6. Recovery references

The P0 recovery reference is process-local development evidence. It does not survive process restart, is not backed by a durable idempotency ledger and does not prove whether a client received a response. Production implementation requires a durable outcome record keyed by request ID, operation digest, commit index/generation and authority epoch.

A production query must return one of:

```text
NOT_FOUND
REJECTED_BEFORE_DISPATCH
NOT_COMMITTED
COMMITTED
OUTCOME_UNKNOWN
REVOKED_OR_STALE_EPOCH
```

It must never recreate an external effect while answering the query.

## 7. Production audit requirements

Before promotion beyond P0, the audit subsystem requires a versioned structured schema, descriptor-relative no-follow file/device adapters, record framing, checksums or authenticated chaining, rotation, fsync semantics, disk-full behavior, multi-device policy, redaction tests, clock fields, sequence integrity, crash recovery, retention and independent review.

`qualification=false`, `compatibility_claim=false`, `production_supported=false`, `authority_effect=NONE`.
