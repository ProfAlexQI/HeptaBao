# HeptaBao H03 Protocol Contract V1

## Scope

This contract defines the P0 request envelope and the minimum H03 semantics needed before framework or TLS selection. It is deliberately narrower than full OpenBao compatibility.

## Bounds

| Surface | Bound |
|---|---:|
| HTTP head | 16 KiB |
| body | 1 MiB |
| request target | 2 KiB |
| header count | 64 |
| one header value | 8 KiB |
| request budget | 60 seconds in caller-supplied monotonic ticks |

## Parsing invariants

- HTTP/1.1 only.
- CRLF only; bare CR/LF and NUL are rejected.
- Request head and target are ASCII.
- Exactly one non-empty Host header is required.
- Duplicate headers and `Transfer-Encoding` are rejected.
- `Content-Length` is decimal canonical form and exactly matches the body.
- Header names use the HTTP token character set; values do not contain controls, tabs, leading/trailing OWS or multiple leading spaces.
- Paths begin with `/v1/`; duplicate slash, dot segment, backslash, NUL, fragment and encoded slash/backslash are rejected.
- Percent escapes use uppercase hex and may not encode an unreserved character.
- Query keys are unique and canonicalized into lexical order; operations not defining query semantics reject all query parameters.

## Operation registry

P0 registers only health, init, seal status, seal, unseal and KV v1 read/write/list/delete. Unknown method/path combinations fail closed. Classification happens after target canonicalization and before authentication or mutation.

## Deadline

The caller provides `received_at`, `deadline` and the actual dispatch-time `now` from one monotonic clock domain. Deadline must be after receipt, within the maximum budget, and later than actual dispatch time. A clock regression or expired request cannot dispatch.

## Secret type

`SecretBytes` owns secret bytes, uses length-aware comparison, redacts `Debug`, and overwrites owned bytes on drop. This is best-effort process-memory hygiene, not a claim that compilers, allocators, copies, swap or core dumps cannot retain data.

## Audit semantics

The request audit precedes dispatch. A mutating response is acknowledged only after response audit. If the operation committed but response audit failed, the caller receives an explicit recovery reference and must not blindly retry.

## Exclusions

Chunked transfer, HTTP/2/3, proxy forwarding, namespaces, wrapping, leases, plugins, Agent/Proxy behavior, TLS and full OpenBao error/normalization compatibility are outside P0.
