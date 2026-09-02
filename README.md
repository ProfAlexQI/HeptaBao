# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.4.7 post-merge truth and external admission**.
- Current integration baseline: signed **V1.4.6 authoritative recovery closure** merge `54d524214df443752a2ecaeff6d4a05625bf52c7`, tree `c22288f561fdd711e908ce8a70c0116601d519e5`.
- Inherited immutable baselines: **V1.4.5 security invariant closure** and **V1.4.4** module-documentation closure recorded by `planning/HEPTABAO_MODULE_DOCUMENTATION_COVERAGE_V1_4_4.yaml`.
- Current implemented foundation: the inherited 19-crate safety/recovery kernel, source-bound module documentation, and strict fail-closed external completion admission.
- Current Cargo workspace documentation: **19 / 19** crates have source-bound developer guides under `docs/modules/`.
- Qualification: **false**.
- Compatibility claim: **false**.
- Dependency selections: **none with production authority**.
- Production, migration, release and mixed-cluster authority: **false**.
- Supported production versions: **none**.

The repository is **not production-deployable** and is **not a production-deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in source, tests or CI.

## Current normative entry points

1. `docs/CURRENT_DOCUMENTATION.md`
2. `docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md`
3. `planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml`
4. `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml`
5. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml`
6. `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml`
7. `docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md`
8. `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md`
9. `planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml`
10. `.github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml`

## Architecture boundary

The current code remains a safety-oriented kernel and loopback-only P0 development server. A production composition root, policy, identity, token, lease, namespace, plugin host, secrets engines, Raft/HA, CLI, Agent, Proxy and full OpenBao compatibility remain later product work. Target documents and unexecuted evidence templates do not imply that those capabilities are implemented or qualified.

## Evidence and authority boundary

Repository-controlled tests can validate source and admission logic but cannot manufacture live branch protection, accountable independent identities, legal disposition, 24x7 operations, isolated signing custody, restricted Oracle transfer, destructive storage-laboratory evidence or independently controlled reproduction. Those blockers close only through externally verified, current, scope-bound completion objects.

## Development

Run the current renderer, current gate and the complete inherited plan/platform/Oracle regressions:

```text
python scripts/render_plan_v1_4_7.py --check
python scripts/validate_plan_v1_4_7.py
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```

Exact current source and prospective-merge identities come from the active pull request and immutable read-only workflows, not from an unversioned `latest` alias.
