# HeptaBao Authbus Integration Contract V1

## Trust boundary

Authbus establishes an external subject. HeptaBao remains the only writer and evaluator for policy, internal identity linkage, token, lease, namespace, audit, seal and authorization state.

## Assertion fields

A V1 assertion contains version, issuer, audience, subject, key ID, issue/expiry Unix seconds, request digest, 128-bit nonce and signature. Identity strings are bounded ASCII without controls, whitespace or backslash. Signature and assertion sizes are bounded.

## Request binding

The signed request digest covers a length-prefixed canonical encoding of:

1. domain separator;
2. HeptaBao request ID;
3. method;
4. canonical request target;
5. exact Host value;
6. body bytes.

This prevents method/path/body/host confusion and assertion reuse across requests.

## Time model

The wire format uses Unix seconds because process-local monotonic instants have no cross-process meaning. Maximum assertion TTL is 30 seconds and future issue time skew is bounded to 5 seconds. Expired, zero/negative lifetime, overlong lifetime, overflow and excessive future issue time fail closed.

## Verification ordering

```text
policy validation
→ assertion shape/version
→ issuer/audience/key allowlist
→ lifetime and current time
→ canonical request digest
→ signature verification
→ atomic replay-cache check-and-record
→ internal authenticated identity input
```

Recording the nonce occurs only after signature and request binding verify. A replay cache failure is an authentication failure.

## Authorization effect

The only representable value is `AuthorizationEffect::None`. A verified assertion cannot directly grant a capability or token. Downstream HeptaBao identity and policy packages must independently authorize the operation.

## Provider boundary

The crate defines digest, signature-verifier and replay-cache traits. Test providers are non-cryptographic and may never be used outside tests. Production algorithms, key distribution, rotation, revocation, HA replay-store consistency and signer custody require separate candidate selection and qualification.

## Required qualification cases

- request/method/target/body/Host mismatch;
- issuer, audience and key confusion;
- expiry, future skew and clock rollback;
- nonce replay, concurrent duplicate and cache failure;
- signature malleability and malformed length fields;
- HA forwarding and replay-cache fencing;
- parser fuzzing and cross-language canonical-byte conformance;
- red-team review proving no authorization authority crosses the adapter.
