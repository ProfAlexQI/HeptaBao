# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.2**
- Current maturity: **governance / Oracle / platform bakeoff implementation**
- Qualification: **false**
- Compatibility claim: **false**
- Production, migration, release and mixed-cluster authority: **false**
- Supported production versions: **none**

The repository contains governance contracts, Oracle inventory/normalization scaffolding, dependency qualification tooling and OpenRaft/TLS/runtime probes. It is **not yet a deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in the repository or CI.

## Normative entry points

1. `docs/plan/HEPTABAO_MASTER_DEVELOPMENT_PLAN_V1_2.md`
2. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1.yaml`
3. `planning/HEPTABAO_CANONICAL_PROJECT_STATE_V1.yaml`
4. `planning/HEPTABAO_BLOCKER_REGISTER_V1.yaml`
5. `planning/HEPTABAO_WORK_PACKAGE_CATALOG_V1_2.yaml`

A resolved state must be generated from the exact checked-out commit/tree. Historical V1.1 status and queue files are retained for audit history but are not the V1.2 current-state authority.

## Security boundary

A green CI run, merged PR, tag, candidate comparison or qualification receipt grants no operational authority. Authority requires a separate signed, scoped, expiring and revocable grant whose full trust and revocation graph verifies.
