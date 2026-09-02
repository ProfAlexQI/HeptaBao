# HeptaBao External Completion Admission Protocol V1

## Purpose

This protocol admits completion evidence for `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` without converting repository automation, templates or self-assertions into external facts. Closure admission is fail-closed and binds one exact reviewed head, base, two-parent merge, plan digest and normative-manifest digest.

## Envelope and schema

Every candidate uses `heptabao.external-completion-evidence.v1` and must validate against `schemas/heptabao_external_completion_evidence_v1.schema.json`. Unknown properties are rejected. Non-closure validation checks only shape and immutable authority nonclaims; it never promotes an `UNEXECUTED` or pending object.

Closure mode additionally requires:

- exact head, tree, base, merge, merge tree and ordered merge-parent identities supplied independently by the admitting caller;
- exact plan and normative-manifest SHA-256 digests supplied independently by the admitting caller;
- the complete blocker-specific mandatory case inventory, with every case `PASS` and evidence-digest bound;
- all blocker-specific artifact kinds, each digest bound and held at an absolute URN or HTTPS custody reference;
- distinct actors for every required role, current issuer-bound accountable credentials, explicit independence and zero unresolved conflicts;
- blocker-specific control-separation identifiers and explicit inequality between primary and external/control roots;
- no open Critical, High or Unclassified finding;
- one payload-bound signature from every required role;
- a caller-supplied external cryptographic verifier for every signature.

## Signature contract

The envelope never proves its own signatures. A text field such as `verification: VALID` is prohibited by the schema and cannot close a blocker.

Each signer signs a domain-separated canonical payload:

```text
HEPTABAO_EXTERNAL_COMPLETION_EVIDENCE_V1\0
  || canonical-json({
       domain,
       envelope-with-empty-signatures,
       signature-metadata
     })
```

The signed envelope binds each actor’s stable identity, organization, credential identifier and issuer, credential validity interval and revocation authority. Signature metadata additionally binds signer, accountable role, key, algorithm, signing and expiry times, trust-root identifier, transparency-checkpoint digest and revocation-evidence digest. The envelope carries the resulting payload SHA-256. Admission recomputes it before invoking the verifier.

The external verifier receives the canonical payload plus signature metadata and bytes. It must independently validate the signature, key role/scope, current trust root, transparency inclusion and revocation state. Closure fails unless the verifier returns an exact result containing:

```text
verified=true
matching signer_id
matching accountable role and organization
matching current credential_id with credential_status=CURRENT_SCOPE_BOUND
matching key_id and trust_root_id
matching payload_digest
revocation_status=CURRENT
transparency_status=INCLUDED
```

Repository tests may inject a deterministic callback only to test validator control flow. Test, mock or example algorithms are rejected in real closure mode.

## Mandatory case and artifact catalogs

The validator owns a minimum case catalog and artifact-kind catalog for every blocker. Supplying one generic `PASS` row, omitting a negative/control case, omitting a raw-evidence manifest or relabelling a partial run as complete fails closure. Additional cases and artifacts are allowed, but duplicate IDs/kinds are rejected.

The catalogs cover, among other things:

- ruleset API readback and blocked bypass/force-push/deletion/look-alike checks;
- program, security and storage reviews with identity and revocation checks;
- every required legal scope and signer-authority check;
- private intake, continuous primary/backup coverage, tabletop and freeze/revocation drills;
- key ceremonies, transparency, rotation, compromise and consumer revocation;
- Oracle ACL separation, real behavior captures, deterministic sanitization and signed transfer;
- controller-proven power cuts, durability boundaries, acknowledged-write preservation, corruption and repeat-recovery controls;
- independent source acquisition, dependency resolution, full head/merge execution, artifact comparison, normalizer control and divergence review.

## Invocation

Planning-only shape validation:

```text
python scripts/validate_external_completion_evidence_v1.py candidate.json
```

Closure admission requires every expected identity/digest and an external verifier executable:

```text
python scripts/validate_external_completion_evidence_v1.py \
  --require-closure \
  --expected-commit <40-hex-head> \
  --expected-tree <40-hex-head-tree> \
  --expected-base-commit <40-hex-base> \
  --expected-merge-commit <40-hex-merge> \
  --expected-merge-tree <40-hex-merge-tree> \
  --expected-merge-parent-one <40-hex-base> \
  --expected-merge-parent-two <40-hex-head> \
  --expected-plan-digest sha256:<64-hex> \
  --expected-manifest-digest sha256:<64-hex> \
  --signature-verifier /isolated/bin/heptabao-signature-verifier \
  candidate.json
```

The verifier executable reads one JSON verification request on standard input and returns the exact verification result on standard output. Nonzero exit, malformed output, mismatched identity, stale/expired signature, missing transparency inclusion or non-current revocation status fails closure.

## Templates and authority boundary

Templates under `qualifications/external/templates/` are deliberately `UNEXECUTED`, contain null source identities and no signatures, and can never pass closure mode. Repository ownership, administrator access, CI success, a generated receipt, a self-signed test key or a populated `verification` field cannot manufacture independent people, legal authority, operational coverage, isolated custody, restricted Oracle provenance, destructive laboratory control or independent reproduction.

Admission closes only the named factual blocker for its exact scope after authentic verification. It does not by itself grant compatibility, provider selection, qualification, production, migration or release authority.
