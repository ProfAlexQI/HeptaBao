# HeptaBao V1.3 Threat Model Delta

## Scope

This delta covers the strict H03 protocol crate, the Authbus assertion contract and the `HB-P0-DEV-MEMORY` server. It supplements the system threat model and grants no qualification or authority.

## Assets

- development root token and unseal key;
- in-memory KV values;
- request identity, canonical operation and deadline;
- audit happens-before and commit outcome;
- Authbus subject, signing-key identity, nonce and request binding;
- exact source, lock graph and test evidence.

## Trust boundaries

1. untrusted TCP client → strict HTTP parser;
2. parsed request → operation registry and state guard;
3. process environment → development credential loader;
4. process → audit filesystem path;
5. Authbus process/domain → assertion verifier;
6. verified external identity → HeptaBao identity/policy evaluation;
7. repository source → CI runner and evidence artifacts.

## Threats and controls

| Threat | Control | Residual risk / required later evidence |
|---|---|---|
| HTTP request smuggling | CRLF-only, exact Content-Length, duplicate-header and Transfer-Encoding rejection | HTTP/2/3, proxies and framework adapters remain unqualified |
| Path and normalization confusion | `/v1/` canonical target, no duplicate slash/dot/backslash/encoded slash, uppercase canonical escapes | Full upstream normalization corpus remains H01-blocked |
| Host/routing confusion | exactly one Host header; P0 requires exact bound loopback address | trusted proxy and cluster forwarding are out of scope |
| Deadline bypass or stale request dispatch | receipt/deadline/actual-dispatch monotonic checks | distributed deadline propagation remains future work |
| Secret leakage through Debug | explicit redacted Debug and best-effort zeroization | allocator copies, swap, core dump and compiler-elision evidence remain absent |
| Audit bypass before mutation | request audit is mandatory; failure blocks dispatch | production multi-device audit quorum is not implemented |
| Ambiguous retry after commit | post-commit audit failure returns committed=true plus recovery reference | durable idempotency ledger is not implemented in P0 |
| Audit path symlink attack | absolute create-new path and symlink/non-directory component rejection | pure-std path inspection has TOCTOU; descriptor-relative no-follow adapter required |
| Authbus assertion replay | bounded nonce cache check-and-record after signature verification | HA-consistent replay store and epoch fencing remain H21-WP12 |
| Authbus method/path/body confusion | length-prefixed digest binds request ID, method, canonical target, Host and body | cross-language canonical-byte conformance still requires independent execution |
| Cross-process monotonic-time misuse | assertion validity uses Unix seconds with bounded skew | trusted time source and rollback monitoring remain deployment controls |
| Authentication confused with authorization | verified result can only carry `AuthorizationEffect::None` | policy/identity integration and red-team review remain required |
| Test provider promoted to production | production digest/signature provider is absent; test provider exists only under cfg(test) | candidate bakeoff, key custody and algorithm policy remain blocked |
| Automatic snapshot purges replay source | in-memory replay topology uses `SnapshotPolicy::Never`; manual snapshot cases remain | exact-head OpenRaft matrix must execute |
| Fixed leader assumed after process pause | bounded consensus-leader discovery after resume | true per-node process suspension remains external-lab work |

## Abuse cases

The following must fail closed: duplicate Host, body without canonical length, conflicting framing, encoded slash, unknown operation, expired request, sealed secret access, missing/weak/equal development credentials, rejection-audit outage, request-audit outage, forged Authbus signature, key/issuer/audience mismatch, future/expired assertion, replayed nonce and any attempt to represent Authbus verification as authorization.

## Residual boundary

P0 deliberately lacks durable storage, HA, TLS, namespace isolation, production authentication, lease/external-effect machinery and OpenBao compatibility. Successful local or CI execution cannot be used to protect real secrets. Independent security review, fuzzing, external storage laboratory evidence and authority remain mandatory.
