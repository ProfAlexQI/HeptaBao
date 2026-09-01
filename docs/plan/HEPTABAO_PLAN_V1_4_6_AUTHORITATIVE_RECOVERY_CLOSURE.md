# HeptaBao Plan V1.4.6 — Authoritative Recovery Closure

## 1. Baseline and authority boundary

This tranche rebuilds a clean candidate from immutable V1.4.5 source commit
`936cb5599d206cea895de2ae04a1289a0b3a0326`, tree
`7c2ac2adc8eff42360950dcd425eb20e894c3c22`. It incorporates only reviewed
source changes from the V1.4.6 development branch; diagnostics, source-writing
scripts and materializer workflows are deliberately excluded.

Source, tests and CI evidence do not select a provider, qualify a platform,
authorize migration, establish compatibility, or grant production/release
authority.

## 2. Objective

Close the remaining repository-controlled gaps in the V1.4.5 security kernel:

1. hold current rollback-anchor authority continuously across target admission
   and irreversible recovery publication;
2. replace the target `is_empty`/`stage` time-of-check/time-of-use split with
   atomic empty-target staging;
3. recover interrupted durable mutations from authoritative store and journal
   state without generic reconciliation;
4. prove append-unknown fencing with a record persisted before the injected
   append error;
5. create every single-node store control and bundle file owner-only on Unix;
6. give pull-request exact-head and prospective-merge checks distinct,
   non-colliding provenance; and
7. bind these guarantees to a clean source tree, crash matrix, module addenda,
   semantic validator and hostile validator tests.

## 3. Rollback-anchor publication fence

A checkpoint reread immediately before `publish` is insufficient: another
writer can advance the anchor after the reread and before the effect. The
provider-neutral anchor therefore exposes a closure-based current-checkpoint
fence. The provider must use the same serialization primitive for the fence and
for compare-and-swap advancement.

```text
authenticate archive
→ verify checkpoint is current
→ acquire provider current-checkpoint fence
→ compare exact checkpoint while fence is held
→ atomically stage only into an empty target
→ publish and obtain exact receipt
→ release fence
```

The closure API prevents the coordinator from accidentally releasing the
provider fence between verification and publication. The in-memory hostile
provider proves that a competing lock acquisition cannot succeed while
`publish` executes. A future remote provider must implement equivalent lease or
transaction semantics and fail closed on lease uncertainty; this tranche does
not qualify such a provider.

## 4. Atomic target admission

`RecoveryTarget::stage_if_empty` combines target emptiness verification and
staging under the target provider's own writer fence. It returns a distinct
`TargetNotEmpty` disposition rather than relying on a prior advisory read.
The staged capability remains provider-private and is consumed exactly once by
`publish`.

## 5. Authoritative mutation recovery

The storage provider computes an exact commit descriptor before the ledger
records `IntentCommitted`. The descriptor binds previous generation, exact next
generation and state digest. It is metadata, not proof that a journal record
exists and not an authority token.

After an interrupted commit, `JournaledDurableCore` derives the recovery target
from the replayed operation ledger and asks the store to classify authoritative
state:

- exact generation and digest visible: record `StateCommitted`;
- exact candidate absent and previous generation current: record
  `AbortedBeforeStateCommit`;
- any divergent state: remain fenced and return conflict.

The file store may complete publication of one exact immutable orphan bundle
only when that bundle authenticates and matches the ledger-derived descriptor.
The file journal similarly reconciles at most one exact authenticated next
orphan before replay.

## 6. Append-unknown and file permissions

Operation-ledger hostile evidence persists the event first and then returns an
injected append error. The ledger enters `ReplayRequired`, rejects all writes,
replays authoritative journal state, and reconstructs the persisted operation.

On Unix, store marker, `CURRENT`, temporary control files and immutable
generation bundles are created with mode `0600`. Directory ownership and
filesystem/controller durability remain deployment and qualification concerns.

## 7. Clean CI provenance

The permanent V1.4.6 workflow is pull-request-only and read-only. Its matrix
checks the immutable PR head and GitHub's prospective two-parent merge
candidate under distinct job names. No push job may reuse those contexts.
Execution-only materializers and diagnostics are forbidden from the candidate
tree.

## 8. Required evidence

The immutable candidate must pass:

```text
python scripts/validate_plan_v1_4_6.py
python -m unittest discover -s tests/plan -p 'test_plan_v1_4_6.py' -v
python scripts/validate_plan_v1_4_5.py
python -m unittest discover -s tests/plan -p 'test_plan_v1_4_5.py' -v
python scripts/validate_module_documentation_v1_4_4.py
python -m unittest discover -s tests/plan -p 'test_module_documentation_v1_4_4.py' -v
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```

Independent reviewers must bind acceptance to the exact source SHA and current
prospective merge SHA. Administrator privilege is not a review receipt.

## 9. Explicitly carried work

This tranche still does not implement or qualify the production composition
root, policy, identity, token, lease, namespace, plugin host, secrets engines,
Raft/HA, CLI, Agent, Proxy, production KMS/HSM, remote rollback provider,
backup ceremony, controller power-cut qualification, online migration, or full
OpenBao compatibility.

## 10. Completion rule

HB-BLK-REPO-049 through HB-BLK-REPO-055 close only when the clean immutable
candidate passes exact-head and prospective-merge gates and independent review
accepts the fence, recovery, permissions, CI and documentation claims. External
and control blockers remain open until their real completion objects exist.
