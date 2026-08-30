# HeptaBao Plan V1.3.1 — Repository Gap Closure

**Plan ID:** `HEPTABAO-PLAN-2026-08-28`  
**Revision:** `1.3.1`  
**Status:** `NORMATIVE_REPOSITORY_GAP_CLOSURE_INPUT`  
**Authority effect:** `NONE`

## 1. Purpose

V1.3.1 converts the materialized V1.3 source into one ordinary reviewable integration branch and closes the repository-controlled defects found by the V1.3 audit. It does not alter any legal, independent-review, signing, incident-operation, restricted-Oracle, power-cut-laboratory, compatibility, qualification or authority boundary.

The canonical implementation lane for this closure is `codex/plan-v1.3-gap-closure-v2`. The source was anchored from materialized commit `b694d24a16ee9714fb888e72aca86f16effd1761` and is reviewed through PR #45. Compressed source transport and CI-authored source publication are not normal delivery mechanisms.

## 2. Repository-controlled closure scope

The patch must provide all of the following on one exact remote commit and tree:

1. a total request-read deadline that cannot be extended by byte trickling;
2. a hard concurrent-connection bound with fail-closed saturation behavior;
3. a request-attempt identity allocated before parsing so malformed, Host-invalid and socket-failed requests can be audited;
4. stable transport rejection detail codes;
5. an optional bounded single-use `X-HeptaBao-Request-Id` development contract, separated from the future HA Authbus replay authority;
6. HTTP 204 wire responses with zero body bytes and `Content-Length: 0`;
7. durable-store writes that never recreate an opened storage root after deletion or replacement;
8. legacy adoption that rejects unresolved authoritative-data temporary artifacts;
9. one read-only exact-head workflow covering every workspace crate, plans, tests and H02 probes;
10. machine-checked current status, transport test vectors, Authbus request-ID lifecycle and audit-outcome documentation.

## 3. Exact execution gates

### Gate A — plan and policy

- all inherited V1.1–V1.3 validators pass;
- `scripts/validate_plan_v1_3_1.py` passes;
- all Python regression suites pass;
- active workflows remain read-only and checkout credentials are not persisted;
- no repository-controlled state is promoted from source presence alone.

### Gate B — root Rust

On Rust `1.98.0` and the committed root lock:

```text
cargo fmt --all -- --check
cargo test --locked --workspace --all-targets
cargo clippy --locked --workspace --all-targets -- -D warnings
```

### Gate C — P0 transport

The exact binary must demonstrate:

- loopback-only startup;
- normal health/init/unseal/KV behavior;
- no body on HTTP 204;
- duplicate Host and Host/listener mismatch rejection with audit evidence;
- duplicate client request-ID rejection;
- a partial request cannot remain connected past the total read deadline;
- audit artifacts are non-empty and contain the expected stable detail codes.

### Gate D — H02 exact-head

The same exact source must compile and lint the OpenRaft graph on Rust `1.88.0` and `1.98.0`, then execute all 24 in-memory, hostile, blocker and durable entries. Any failed, blocked, unknown, malformed, missing, duplicate, unexpected or unexecuted entry fails the aggregate.

### Gate E — independent closure

Critical repository blockers require current review receipts from distinct accountable reviewers. Repository automation cannot issue those receipts for itself.

## 4. External boundary

The following remain real external actions and cannot be closed by source changes:

- `HB-BLK-CTRL-001`: enforced canonical-branch ruleset;
- `HB-BLK-EXT-001`: independent accountable reviewer identities;
- `HB-BLK-EXT-002`: signed legal, license, clean-room, trademark, patent and export disposition;
- `HB-BLK-EXT-003`: private disclosure, 24x7 incident ownership and drills;
- `HB-BLK-EXT-004`: isolated signing, transparency and emergency revocation;
- `HB-BLK-EXT-005`: restricted Oracle capture and signed transfer;
- `HB-BLK-EXT-006`: independently operated filesystem/power-cut laboratory evidence;
- `HB-BLK-EXT-007`: independently operated reproduction.

Every external blocker remains `EXTERNAL_ACTION_REQUIRED` until its declared completion object verifies. Missing evidence is not interpreted as success.

## 5. Promotion rules

```text
SOURCE_PRESENT
→ COMPILES
→ EXECUTED_PASS
→ INDEPENDENTLY_REVIEWED
→ QUALIFIED
→ COMPATIBILITY_CLAIM
→ SCOPED_AUTHORITY_GRANT
```

No transition is implicit. V1.3.1 fixes `qualification=false`, `compatibility_claim=false`, `selected_candidates=[]`, `selection_effect=NONE` and `authority_effect=NONE`.

## 6. Stop conditions

The repository-controlled patch is technically complete only when Gates A–D pass on one exact head. It is review-complete only when Gate E receipts exist. Program-wide gap closure additionally requires all eight external/control completion objects. Until then the truthful state remains technical remediation in review with external action required.
