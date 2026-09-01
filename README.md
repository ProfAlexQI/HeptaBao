# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.4.5 security invariant closure**.
- Exact predecessor: **V1.4.4 module documentation closure** (`489a104450ff48c49e7fb61e167e566ea5e0e6c7`).
- Current implemented foundation: strict P0 protocol, Authbus contracts, durable generation store, authenticated journal, fail-stop operation/key ledgers, live-anchor-authorized recovery, exact receipt validation and Linux descriptor-rooted ancestor walking/writer fencing.
- Current Cargo workspace documentation: **19 / 19** crates have developer guides.
- Qualification: **false**.
- Compatibility claim: **false**.
- Dependency selections: **none with production authority**.
- Production, migration, release and mixed-cluster authority: **false**.
- Supported production versions: **none**.

The repository is **not production-deployable**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in source, tests or CI.

## Current normative entry points

1. `docs/CURRENT_DOCUMENTATION.md`
2. `docs/plan/HEPTABAO_PLAN_V1_4_5_SECURITY_INVARIANT_CLOSURE.md`
3. `planning/HEPTABAO_V1_4_5_SECURITY_INVARIANT_STATUS.yaml`
4. `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_5.yaml`
5. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_5.yaml`
6. `docs/security/HEPTABAO_SECURITY_INVARIANT_CLOSURE_V1.md`
7. `planning/HEPTABAO_MODULE_DOCUMENTATION_COVERAGE_V1_4_4.yaml`
8. `docs/modules/README.md`
9. `docs/modules/MODULE_DOCUMENTATION_STANDARD_V1.md`
10. `.github/workflows/plan-v1.4.5-security-invariant-closure.yml`

## Architecture boundary

The current code is a set of safety-oriented kernel components and a loopback-only P0 memory server. A production composition root, policy, identity, token, lease, namespace, plugin host, secrets engines, Raft/HA, CLI, Agent, Proxy and full OpenBao compatibility remain future product work. Target-architecture documents do not imply that these modules exist.

## Evidence and authority boundary

Technical source, tests, CI, qualification, compatibility and operational authority are distinct. External repository controls, independent reviews, legal disposition, incident operation, isolated signing, restricted Oracle transfer, power-cut/filesystem laboratory evidence and independent reproduction close only through their declared real completion objects.

## Development

Read the guide for the crate you are changing under `docs/modules/`, update it in the same commit, and run:

```text
python scripts/validate_plan_v1_4_5.py
python -m unittest discover -s tests/plan -p 'test_plan_v1_4_5.py' -v
python scripts/validate_module_documentation_v1_4_4.py
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```

Source baseline for V1.4.5: `489a104450ff48c49e7fb61e167e566ea5e0e6c7` / `a567e8feb90077de5e3a8e540f07a89192264338`. V1.4.4 remains the inherited **19 / 19** module-documentation coverage revision.
