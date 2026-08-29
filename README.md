# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.2**
- Current operational amendment: **V1.2.1**
- Current maturity: **governance / Oracle / platform bakeoff implementation**
- Qualification: **false**
- Compatibility claim: **false**
- Dependency selections: **none**
- Production, migration, release and mixed-cluster authority: **false**
- Supported production versions: **none**

The repository contains governance contracts, Oracle inventory/normalization scaffolding, dependency qualification tooling and OpenRaft/TLS/runtime probes. It is **not yet a deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in the repository or CI.

## Normative entry points

1. `docs/plan/HEPTABAO_MASTER_DEVELOPMENT_PLAN_V1_2.md`
2. `docs/plan/HEPTABAO_PLAN_V1_2_1_EXECUTION_DEEPENING.md`
3. `docs/plan/HEPTABAO_PLAN_V1_2_1_EXACT_HEAD_EVIDENCE_ADDENDUM.md`
4. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1.yaml`
5. `planning/HEPTABAO_CANONICAL_PROJECT_STATE_V1.yaml`
6. `planning/HEPTABAO_BLOCKER_REGISTER_V1.yaml`
7. `planning/HEPTABAO_EXTERNAL_ACTION_PACKAGE_CATALOG_V1.yaml`
8. `planning/HEPTABAO_WORK_PACKAGE_CATALOG_V1_2.yaml`
9. `docs/execution/HEPTABAO_BLOCKER_CLOSURE_OPERATING_CONTRACT_V1.md`
10. `docs/execution/HEPTABAO_H02_EXACT_HEAD_MATRIX_EXECUTION_SPEC_V1.md`

A resolved state must be generated from the exact checked-out commit/tree. Historical V1.1 status and queue files are retained for audit history but are not the V1.2 current-state authority.

## Exact-head H02 execution boundary

The current H02 aggregate gate must execute **24 fixed entries**: two effective Rust toolchains × three fixed seeds × four OpenRaft probe kinds. Every entry preserves stdout, stderr and exit code, and is independently checked at the application-result layer. A zero process exit cannot hide `EXECUTED_FAIL`, malformed JSON, a failed case or an authority-field drift. The machine summary remains unqualified and authority-free even when all technical entries pass.

## Blocker boundary

Repository-controlled remediation is not closed until exact-head CI, complete matrix evidence and required independent review exist. Repository settings, reviewer identities, legal conclusions, incident operations, isolated signing, restricted Oracle capture, power-cut laboratories and independent reproduction remain `EXTERNAL_ACTION_REQUIRED` until their one-to-one action packages produce signed, current and independently verified completion objects.

## Security boundary

A green CI run, merged PR, tag, candidate comparison or qualification receipt grants no operational authority. Authority requires a separate signed, scoped, expiring and revocable grant whose full trust and revocation graph verifies.
