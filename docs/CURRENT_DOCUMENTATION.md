# HeptaBao Current Documentation

This page is the single current-entry portal. A newer row supersedes an older row only for the named subject; historical documents remain immutable evidence and are not silently rewritten.

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md` |
| current status | `planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml` |
| post-merge V1.4.6 closure receipt | `planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| module documentation standard | `docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md` |
| module index | `docs/modules/README.md` |
| machine-bound module source truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml` |
| external completion admission protocol | `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md` |
| external completion admission catalog | `planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml` |
| current exact-head/merge gate | `.github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml` |

## Inherited immutable set

| Subject | Inherited document |
|---|---|
| V1.4.6 plan | `docs/plan/HEPTABAO_PLAN_V1_4_6_AUTHORITATIVE_RECOVERY_CLOSURE.md` |
| V1.4.6 status | `planning/HEPTABAO_V1_4_6_AUTHORITATIVE_RECOVERY_STATUS.yaml` |
| V1.4.6 blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_6.yaml` |
| V1.4.6 normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_6.yaml` |
| V1.4.6 authoritative recovery protocol | `docs/recovery/HEPTABAO_AUTHORITATIVE_RECOVERY_PROTOCOL_V1.md` |
| V1.4.6 recovery gate | `.github/workflows/plan-v1.4.6-authoritative-recovery-closure.yml` |
| V1.4.5 security regression gate | `.github/workflows/plan-v1.4.5-security-invariant-closure.yml` |
| V1.4.4 module existence gate | `.github/workflows/plan-v1.4.4-module-documentation.yml` |

## Supersession chain

```text
V1.4.2 anchored recovery foundation
  → V1.4.3 descriptor anchoring/writer fencing
  → V1.4.4 complete current-crate documentation
  → V1.4.5 security invariant closure
  → V1.4.6 authoritative recovery closure
  → V1.4.7 post-merge truth and external admission
```

## V1.4.6 post-merge disposition

V1.4.6 exact head `837668cb879683bc60808584d2ebdedd42a397aa` and prospective merge `54d524214df443752a2ecaeff6d4a05625bf52c7` passed their required repository gates. The same exact head received a current GitHub approval, and the signed GitHub merge has tree `c22288f561fdd711e908ce8a70c0116601d519e5`. The V1.4.7 post-merge receipt therefore closes only `HB-BLK-REPO-049` through `HB-BLK-REPO-058` in repository-controlled scope. It does not create an accountable role receipt or close any control/external blocker.

## V1.4.7 reading rule

Each current Cargo workspace crate has one module guide. Public lexical declarations, workspace-internal dependencies, source-file digests and discovered test functions are generated from the exact candidate source and bound in `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml`. Generated tables are source truth for the exact candidate; they do not promise API stability, compatibility or production support.

External completion documents are admitted only through the strict V1.4.7 envelope and validator. Templates are deliberately `UNEXECUTED` and are prohibited from closing a blocker. A green repository workflow cannot manufacture legal advice, independent identities, 24x7 operation, isolated key custody, restricted Oracle transfer, destructive power-cut evidence or separately controlled reproduction.

## Open authority boundary

`HB-BLK-CTRL-001` and `HB-BLK-EXT-001` through `HB-BLK-EXT-007` remain open until live, current, independently verifiable completion objects are admitted. Product composition, compatibility, platform qualification, provider selection, migration, production and release authority remain false.
