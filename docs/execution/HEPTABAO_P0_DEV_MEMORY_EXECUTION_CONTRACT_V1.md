# HeptaBao P0 Development Memory Execution Contract V1

## Profile

`HB-P0-DEV-MEMORY` is a disposable, loopback-only engineering profile. It is not compatible, durable, available, replicated or production supported.

## Start contract

The binary requires:

- `HEPTABAO_P0_BIND`, defaulting to `127.0.0.1:18200`, and rejects a non-loopback IP;
- `HEPTABAO_P0_DEV_TOKEN`;
- `HEPTABAO_P0_DEV_UNSEAL_KEY`;
- `HEPTABAO_P0_AUDIT_PATH`, an absolute new file path.

The token and unseal key must be distinct and at least 24 bytes. The audit file is created with create-new semantics. Existing files, symlink components and non-directory parent components are rejected. Pure-std path inspection cannot eliminate every platform TOCTOU; production audit devices require descriptor-relative, no-follow platform adapters and independent review.

## State machine

Initial state is uninitialized and sealed. Init marks initialized but stays sealed. Unseal requires the injected development key. Seal requires authentication while unsealed. KV v1 requires initialization, unsealed state and the development token.

## Audit ordering

- rejected requests are audited; if rejection audit is unavailable, the response is 503;
- accepted requests are audited before dispatch;
- request-audit failure prevents mutation;
- response audit records committed/not-committed outcome;
- post-commit audit failure returns 503 with `committed=true` and a recovery reference.

## Socket execution

Each TCP connection carries exactly one HTTP/1.1 request and receives `Connection: close`. Read and write timeouts are five seconds. Host must exactly equal the listener's actual local address, including the assigned ephemeral port.

## Test matrix

- fresh health = 501 and sealed;
- init = committed, credentials not returned;
- unseal wrong/correct key;
- authenticated and unauthenticated KV operations;
- sealed rejection;
- exact Host and request-smuggling negatives;
- expired request non-dispatch;
- request, rejection and response audit failure ordering;
- new absolute audit file and symlink rejection;
- secret Debug redaction;
- process startup rejects missing/equal/weak credentials and non-loopback bind.

## Exit boundary

A successful P0 test means only that the bounded development contract executed on the exact source. It does not close H01 compatibility, H02 production dependency selection, durable storage, security review or any authority gate.
