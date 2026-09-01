# HeptaBao Current Documentation

This page is the single current-entry portal. A newer row supersedes an older
row only for the named subject; historical documents remain evidence and are
not silently rewritten.

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_4_5_SECURITY_INVARIANT_CLOSURE.md` |
| current status | `planning/HEPTABAO_V1_4_5_SECURITY_INVARIANT_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_5.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_5.yaml` |
| security invariant contract | `docs/security/HEPTABAO_SECURITY_INVARIANT_CLOSURE_V1.md` |
| module documentation standard | `docs/modules/MODULE_DOCUMENTATION_STANDARD_V1.md` |
| module index | `docs/modules/README.md` |
| exact module coverage | `planning/HEPTABAO_MODULE_DOCUMENTATION_COVERAGE_V1_4_4.yaml` |
| filesystem contract | `docs/storage/HEPTABAO_DESCRIPTOR_ANCHOR_AND_WRITER_FENCE_V1.md` |

## Supersession chain

```text
V1.4.2 anchored recovery foundation
  → V1.4.3 descriptor anchoring/writer fencing
  → V1.4.4 complete current-crate documentation
  → V1.4.5 security invariant closure
```

V1.4.5 changes security-kernel implementation and its documentation. It does
not supersede the 19/19 crate-coverage measurement from V1.4.4; that coverage is
inherited and revalidated.

## Reading rule

Target-architecture and roadmap documents describe intended future modules.
Only Cargo workspace members and the current as-built module index describe
implemented crates. Status words such as source implemented or test pass never
imply compatibility, qualification, provider selection or production authority.
