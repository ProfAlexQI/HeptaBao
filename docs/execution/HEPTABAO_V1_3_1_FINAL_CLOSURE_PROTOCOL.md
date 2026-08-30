# HeptaBao V1.3.1 Final Repository-Closure Protocol

## Scope

This protocol closes the remaining repository-controlled evidence gaps on PR #45 without converting technical evidence into qualification, compatibility, candidate selection or operational authority.

## Canonical source identity

No static document is permitted to claim a moving pull-request head. Every execution resolves and records repository, exact commit, exact tree, event head, event base and GitHub's synthetic merge commit directly from the event and from Git. The source-head lane and merge-candidate lane must execute different commits on a pull-request event.

The canonical source head must end in an ordinary owner-ratification commit. The ratification commit must be authored outside the `github-actions[bot]` identity, carry the exact subject `chore(provenance): owner-ratify V1.3.1 canonical source tree`, have one parent and preserve its parent's exact Git tree. This republishes the complete reviewed tree through a human-controlled source event while retaining bot-authored ancestors as provenance rather than hiding them.

## P0 evidence classes

The 14 P0 entries are not one homogeneous runtime matrix:

- 11 entries are `RUNTIME_SOCKET_OBSERVED` and must be induced through the loopback socket and bound audit evidence;
- two entries are `EXACT_HEAD_COMPILED_SOURCE_BOUND`: the one-absolute-write-deadline implementation and fallible worker-spawn/capacity-release implementation are compiled, unit-regressed and source-bound, but the socket harness does not claim that it deterministically induced those internal failure paths;
- one entry is `BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND`: controlled Drop/redaction semantics are compiled and tested, but allocator, compiler, swap and post-drop memory inspection are explicitly outside the evidence.

The classified result must report 11 executed passes, two exact-head compiled source-bound passes and one best-effort source-bound pass. It is forbidden to report 14 runtime transport passes.

## Durable legacy-adoption equivalence

The H02 durable lab must preserve and compare the authoritative legacy log bytes and exercise the adopted store through the OpenRaft storage traits. Evidence must compare:

- log state;
- persisted vote;
- committed log identifier;
- all retained log entries;
- retained membership entries;
- the same values after `open_existing` reopens the newly adopted store.

The state-machine adoption proof separately compares client state, last-applied log, stored membership and the reopened state. Creating an initialization marker alone is not a no-data-loss proof.

## Exact head and synthetic merge

On a pull request, one matrix job checks out the exact head and one checks out `github.sha`, verifies that it is distinct from the head, has exactly two parents and that those parents are the event base and event head. Each lane independently executes:

1. every plan validator and Python regression suite;
2. Rust 1.98 root workspace format, tests and strict Clippy;
3. classified P0 socket/audit evidence;
4. Rust 1.88 and 1.98 OpenRaft tests and strict Clippy;
5. the complete 24-entry H02 application matrix;
6. a machine-readable technical receipt bound to the source and runner.

Missing, skipped, blocked, unknown, malformed or ancestor-only evidence fails the lane.

## External boundary

Branch/rules enforcement, independent reviewer identity, legal disposition, incident operation, isolated signing and revocation, restricted Oracle transfer, independent power-cut/filesystem testing and independently operated reproduction remain external action packages. Repository automation cannot manufacture those facts. Technical receipts therefore retain all qualification, compatibility, selection, production, migration and release authority fields as false or `NONE`.
