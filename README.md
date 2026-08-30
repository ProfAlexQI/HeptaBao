# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.3.1 repository gap closure**
- Current inherited base plan: **V1.3**; V1.3.1 is the active repository-closure revision and does not erase the V1.3 lineage.
- Canonical integration lane under review: **`codex/plan-v1.3-gap-closure-v2` / PR #45**
- Current operational foundation: **V1.2.1 + V1.2.2 unified closure + V1.3 P0/Authbus + V1.3.1 repository remediation**
- Current maturity: **governance / Oracle reconciliation / dependency and OpenRaft probes / strict protocol / P0 memory server**
- Repository-controlled source remediation: **committed; exact-head execution and independent review required**
- Qualification: **false**
- Compatibility claim: **false**
- Dependency selections: **none**
- Production, migration, release and mixed-cluster authority: **false**
- Supported production versions: **none**

The repository contains governance contracts, Oracle inventory/normalization scaffolding, dependency qualification tooling, OpenRaft/TLS/runtime probes, a strict protocol crate, Authbus verification contracts and a loopback-only in-memory P0 development server. It is **not a production-deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in the repository or CI.

## Normative entry points

1. `docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md`
2. `planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml`
3. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3_1.yaml`
4. `planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml`
5. `docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md`
6. `docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md`
7. `.github/workflows/plan-v1.3-gap-closure.yml`
8. `docs/plan/HEPTABAO_MASTER_DEVELOPMENT_PLAN_V1_3.md`
9. `docs/plan/HEPTABAO_PLAN_V1_3_AMENDMENT.md`
10. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1.yaml`
11. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3.yaml`
12. `planning/HEPTABAO_CANONICAL_PROJECT_STATE_V1_3.yaml`
13. `planning/HEPTABAO_PLAN_V1_3_STATUS_V1.yaml`
14. `planning/HEPTABAO_BLOCKER_REGISTER_V1_3.yaml`
15. `planning/HEPTABAO_H01_ORACLE_EVIDENCE_RECONCILIATION_V1.yaml`
16. `planning/HEPTABAO_WORK_PACKAGE_CATALOG_V1_2.yaml`
17. `planning/HEPTABAO_WORK_PACKAGE_EXTENSION_V1_3.yaml`
18. `planning/HEPTABAO_P0_WORK_PACKAGE_CONTRACTS_V1.yaml`
19. `docs/protocol/HEPTABAO_H03_PROTOCOL_CONTRACT_V1.md`
20. `docs/auth/HEPTABAO_AUTHBUS_INTEGRATION_CONTRACT_V1.md`
21. `docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md`
22. `planning/HEPTABAO_EXTERNAL_ACTION_PACKAGE_CATALOG_V1.yaml`
23. `docs/execution/HEPTABAO_BLOCKER_CLOSURE_OPERATING_CONTRACT_V1.md`
24. `docs/plan/HEPTABAO_PLAN_V1_2_2_UNIFIED_REPOSITORY_CLOSURE.md`

A resolved state must be generated from the exact checked-out commit/tree. Historical V1.1/V1.2/V1.3 status files are retained for audit history and inherited context; they cannot override the V1.3.1 current repository-closure object.

## V1.3.1 repository closure boundary

V1.3.1 anchors the previously materialized V1.3 source in one ordinary reviewable branch and PR. It adds a total request-read deadline, bounded connection admission, pre-parse request-attempt identity, transport rejection audit, a bounded P0 client request-ID duplicate guard, body-free HTTP 204 responses, H02 active-parent integrity controls, unresolved temporary-artifact guards and one read-only exact-head aggregate workflow.

The Authbus request-ID lifecycle now separates two modes: server-generated P0 audit correlation and client-proposed, assertion-bound production identity. The in-process P0 registry is explicitly not the future HA replay authority. The audit outcome contract records the remaining need for a durable reconciliation ledger and a versioned production audit protocol.

Repository-controlled source markers do not close their blockers by themselves. Technical closure requires one exact remote head to pass all plan/Python checks, Rust 1.98 workspace fmt/test/Clippy, P0 socket and transport behavior, Rust 1.88/1.98 OpenRaft checks and the complete 24-entry application matrix. Critical closure additionally requires current independent review receipts.

## V1.3 executable foundation boundary

V1.3 adds a strict provider-neutral HTTP/request contract, an Authbus authentication-only assertion contract and `HB-P0-DEV-MEMORY`, a disposable loopback-only in-memory server. The profile exercises request canonicalization, seal/init guards, development authentication, KV v1 and audit happens-before semantics. It has no durable storage, compatibility claim, production support or authority.

The effective work-package count is 306: 301 inherited V1.2 packages plus five Authbus packages. The H01 Oracle reconciliation records four locally claimed vectors but zero repository-verifiable transferred vectors. A project issue is not a signed fixture transfer.

## External blocker boundary

Repository settings, independent reviewer identities, legal and clean-room conclusions, private disclosure and incident operations, isolated signing, restricted Oracle capture, filesystem/power-cut laboratories and independently operated reproduction remain `EXTERNAL_ACTION_REQUIRED`. They can close only through their declared signed, current and independently verifiable completion objects. Repository automation must not manufacture or self-attest them.

## Security boundary

A green CI run, merged PR, tag, candidate comparison or qualification receipt grants no operational authority. Authority requires a separate signed, scoped, expiring and revocable grant whose full trust and revocation graph verifies.
