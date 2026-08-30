# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.3**
- Current operational foundation: **V1.2.1 + V1.2.2 unified closure + V1.3 P0/Authbus amendment**
- Current repository closure state: **PR #41 lifecycle materialized remotely; V1.2.2 unified/V1.3 exact-head and external closure required**
- Current maturity: **governance / Oracle reconciliation / dependency probes / strict protocol / P0 memory server**
- Qualification: **false**
- Compatibility claim: **false**
- Dependency selections: **none**
- Production, migration, release and mixed-cluster authority: **false**
- Supported production versions: **none**

The repository contains governance contracts, Oracle inventory/normalization scaffolding, dependency qualification tooling, OpenRaft/TLS/runtime probes, a strict protocol crate, Authbus verification contracts and a loopback-only in-memory P0 development server. It is **not a production-deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in the repository or CI.

## Normative entry points

1. `docs/plan/HEPTABAO_MASTER_DEVELOPMENT_PLAN_V1_3.md`
2. `docs/plan/HEPTABAO_PLAN_V1_3_AMENDMENT.md`
3. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1.yaml`
4. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3.yaml`
5. `planning/HEPTABAO_CANONICAL_PROJECT_STATE_V1_3.yaml`
6. `planning/HEPTABAO_PLAN_V1_3_STATUS_V1.yaml`
7. `planning/HEPTABAO_BLOCKER_REGISTER_V1_3.yaml`
8. `planning/HEPTABAO_H01_ORACLE_EVIDENCE_RECONCILIATION_V1.yaml`
9. `planning/HEPTABAO_WORK_PACKAGE_CATALOG_V1_2.yaml`
10. `planning/HEPTABAO_WORK_PACKAGE_EXTENSION_V1_3.yaml`
11. `planning/HEPTABAO_P0_WORK_PACKAGE_CONTRACTS_V1.yaml`
12. `docs/protocol/HEPTABAO_H03_PROTOCOL_CONTRACT_V1.md`
13. `docs/auth/HEPTABAO_AUTHBUS_INTEGRATION_CONTRACT_V1.md`
14. `docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md`
15. `planning/HEPTABAO_EXTERNAL_ACTION_PACKAGE_CATALOG_V1.yaml`
16. `docs/execution/HEPTABAO_BLOCKER_CLOSURE_OPERATING_CONTRACT_V1.md`
17. `docs/plan/HEPTABAO_PLAN_V1_2_2_UNIFIED_REPOSITORY_CLOSURE.md`

A resolved state must be generated from the exact checked-out commit/tree. Historical V1.1/V1.2 status and queue files are retained for audit history but are not the V1.3 current-state authority.

## V1.3 executable foundation boundary

V1.3 adds a strict provider-neutral HTTP/request contract, an Authbus authentication-only assertion contract and `HB-P0-DEV-MEMORY`, a disposable loopback-only in-memory server. The profile exercises request canonicalization, seal/init guards, development authentication, KV v1 and audit happens-before semantics. It has no durable storage, compatibility claim, production support or authority.

The effective work-package count is 306: 301 inherited V1.2 packages plus five Authbus packages. Four newly discovered repository defects are `REMEDIATION_IMPLEMENTED_LOCAL`; all exact-head Rust/matrix and independent-review evidence remains required.

The H01 Oracle reconciliation records four locally claimed vectors but zero repository-verifiable transferred vectors. A project issue is not a signed fixture transfer.

## V1.2.2 unified reconciliation boundary

The PR40 exact-head evidence hardening is composed with the PR41 explicit `create/reopen/adopt` lifecycle, initialized-generation fail-closed guards, strict-lint repairs and guarded snapshot source binding. PR #41's materializer subsequently executed successfully and published lifecycle head `cd56d815f03c0a62ecb3572fb0ba635e9c5f6b93`; the bot-triggered follow-up checks remain `action_required`, and that branch still does not contain the PR #40/V1.2.2 unified composition or V1.3. The V1.2.2 unified status therefore remains unqualified until one unified remote exact head produces complete execution and independent review evidence.

## Blocker boundary

Repository-controlled remediation is not closed until exact-head CI, complete matrix evidence and required independent review exist. Repository settings, reviewer identities, legal conclusions, incident operations, isolated signing, restricted Oracle capture, power-cut laboratories and independent reproduction remain `EXTERNAL_ACTION_REQUIRED` until their one-to-one action packages produce signed, current and independently verified completion objects.

## Security boundary

A green CI run, merged PR, tag, candidate comparison or qualification receipt grants no operational authority. Authority requires a separate signed, scoped, expiring and revocable grant whose full trust and revocation graph verifies.
