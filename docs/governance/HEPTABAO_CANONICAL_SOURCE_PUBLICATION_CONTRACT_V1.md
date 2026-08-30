# HeptaBao Canonical Source Publication Contract V1

## 1. Scope

This contract distinguishes ordinary review-lane source publication from CI self-publication. It applies to the V1.3.1 integration branch and grants no independent-review, qualification, compatibility, selection, release or production authority.

## 2. Forbidden publication paths

The following cannot establish a canonical implementation head:

- a GitHub Actions job with `contents: write` that creates, rewrites, commits or pushes implementation source;
- a compressed or base64 source payload that is expanded only inside CI;
- a source tree reachable only through an Actions artifact, detached commit or temporary transport branch;
- a commit whose material source bytes are not visible in the ordinary pull-request diff;
- a source receipt that names an ancestor rather than the live frozen head.

These paths may retain diagnostic or historical provenance, but they are not canonical delivery.

## 3. Permitted ordinary review-lane publication

A canonical implementation candidate may be published through either:

1. a maintainer-authored local Git commit pushed to the review branch; or
2. a maintainer-invoked connected GitHub Git Data API commit created outside GitHub Actions.

The second mechanism is permitted only for a final tree-preserving republish. Its commit must have exactly one parent, its Git tree must equal the reviewed parent tree, its message must identify the provenance republish, and the pull request must expose the complete earlier source diff. It cannot introduce new source bytes, rewrite history, bypass review or claim independence.

A GitHub App identity shown as the API committer does not turn this owner-authorized republish into an independent reviewer or signer. The binding is procedural provenance only.

## 4. Frozen candidate and dual admission

After the tree-preserving republish:

- the branch is frozen except for a new superseding candidate;
- the PR body identifies the exact head, tree, base and current GitHub synthetic merge;
- the exact source head executes all plan/Python, root Rust, P0 and H02 gates;
- the distinct GitHub synthetic merge executes the same reusable gate workflow;
- every artifact and technical receipt binds source kind, commit, tree, run, job results and artifact digests;
- source-head success cannot substitute for synthetic-merge success, and vice versa.

## 5. Evidence and authority boundary

A tree-preserving republish proves only that the reviewed bytes were placed on the ordinary integration lane without CI self-publication. It is not a signature, independent review, qualification receipt, compatibility claim or authority grant. Enforced branch rules, accountable independent reviewers, legal disposition, incident operation, isolated signing, restricted Oracle transfer, independent power-cut testing and independent reproduction remain separate external blockers.
