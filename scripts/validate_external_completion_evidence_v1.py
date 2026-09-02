#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import copy
import hashlib
import json
import re
import subprocess
from collections.abc import Callable, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker

REPOSITORY_ID = 1349115072
REPOSITORY_FULL_NAME = "TrillionniumFoundation/HeptaBao"
SCHEMA_NAME = "heptabao.external-completion-evidence.v1"
DOMAIN = b"HEPTABAO_EXTERNAL_COMPLETION_EVIDENCE_V1\x00"
ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "schemas/heptabao_external_completion_evidence_v1.schema.json"
ALLOWED_BLOCKERS = {"HB-BLK-CTRL-001", *{f"HB-BLK-EXT-{i:03d}" for i in range(1, 8)}}
REQUIRED_ROLES = {
    "HB-BLK-CTRL-001": {"repository_administrator", "independent_control_reviewer"},
    "HB-BLK-EXT-001": {"program_reviewer", "security_reviewer", "storage_reviewer"},
    "HB-BLK-EXT-002": {"legal_signer", "independent_program_reviewer"},
    "HB-BLK-EXT-003": {"security_operations", "backup_incident_commander", "independent_observer"},
    "HB-BLK-EXT-004": {"root_key_custodian", "crypto_reviewer", "independent_observer"},
    "HB-BLK-EXT-005": {"oracle_operator", "sanitization_operator", "transfer_custodian", "compatibility_reviewer"},
    "HB-BLK-EXT-006": {"storage_lab_operator", "storage_reviewer"},
    "HB-BLK-EXT-007": {"independent_reproduction_operator", "independent_reproduction_reviewer"},
}
INDEPENDENT_ROLES = {
    "independent_control_reviewer", "program_reviewer", "security_reviewer", "storage_reviewer",
    "legal_signer", "independent_program_reviewer", "independent_observer", "crypto_reviewer",
    "oracle_operator", "sanitization_operator", "transfer_custodian", "compatibility_reviewer",
    "storage_lab_operator", "independent_reproduction_operator", "independent_reproduction_reviewer",
}
REQUIRED_CASES = {
    "HB-BLK-CTRL-001": {
        "live-api-readback", "failing-head-check-blocked", "missing-arbitration-blocked",
        "stale-approval-dismissed", "non-codeowner-rejected", "force-push-rejected",
        "branch-delete-rejected", "admin-bypass-rejected", "lookalike-context-rejected",
    },
    "HB-BLK-EXT-001": {
        "program-review", "security-review", "storage-review", "identity-separation",
        "signature-validation", "revocation-check",
    },
    "HB-BLK-EXT-002": {
        "outbound-license", "contributor-policy", "mpl-interop", "third-party-materials",
        "clean-room", "trademark", "patent", "export-crypto", "source-offer",
        "retention-destruction", "signer-authority", "exact-source-binding",
    },
    "HB-BLK-EXT-003": {
        "private-intake", "primary-coverage", "backup-coverage", "root-material-tabletop",
        "policy-bypass-tabletop", "data-loss-tabletop", "split-brain-tabletop",
        "supply-chain-tabletop", "signer-compromise-tabletop", "oracle-exposure-tabletop",
        "freeze-drill", "revocation-propagation", "independent-observation",
    },
    "HB-BLK-EXT-004": {
        "profile-approval", "root-key-ceremony", "delegated-key-ceremony",
        "offline-trust-root-verification", "transparency-inclusion", "normal-rotation",
        "delegated-compromise", "root-compromise", "consumer-revocation", "independent-observation",
    },
    "HB-BLK-EXT-005": {
        "acl-role-separation", "oracle-profile-freeze", "uninitialized-health", "sealed-health",
        "seal-status", "canonicalization-errors", "malformed-request", "side-effect-observation",
        "deterministic-sanitization", "secret-scan", "semantic-review", "signed-transfer",
        "implementation-receipt",
    },
    "HB-BLK-EXT-006": {
        "environment-attestation", "power-cut-controller-proof", "durability-boundary-matrix",
        "acknowledged-write-preservation", "corruption-rejection", "empty-init-forbidden",
        "recovery-idempotence", "rpo-rto", "negative-missing-fsync", "independent-storage-review",
    },
    "HB-BLK-EXT-007": {
        "environment-independence", "source-identity", "dependency-checksums", "build-from-source",
        "exact-head-matrix", "prospective-merge-matrix", "artifact-comparison",
        "normalizer-control", "divergence-closure", "independence-review",
    },
}
REQUIRED_ARTIFACT_KINDS = {
    "HB-BLK-CTRL-001": {"LIVE_API_READBACK", "NEGATIVE_TEST_BUNDLE", "INDEPENDENT_REVIEW"},
    "HB-BLK-EXT-001": {"ROLE_REGISTRY", "SCOPED_REVIEW_RECEIPTS", "SIGNATURE_VERIFICATION"},
    "HB-BLK-EXT-002": {"LEGAL_DISPOSITION", "REVIEWED_INPUT_MANIFEST", "SIGNATURE_VERIFICATION"},
    "HB-BLK-EXT-003": {"READINESS_ATTESTATION", "DRILL_BUNDLE", "INDEPENDENT_REVIEW"},
    "HB-BLK-EXT-004": {
        "SIGNING_PROFILE", "CEREMONY_TRANSCRIPT", "TRANSPARENCY_CHECKPOINT",
        "REVOCATION_DRILL", "INDEPENDENT_REVIEW",
    },
    "HB-BLK-EXT-005": {
        "RESTRICTED_CAPTURE_REFERENCE", "SANITIZATION_REPORT", "SANITIZED_FIXTURE", "TRANSFER_COMPLETION",
    },
    "HB-BLK-EXT-006": {
        "LAB_ENVIRONMENT_ATTESTATION", "CRASH_MATRIX", "RAW_EVIDENCE_MANIFEST", "INDEPENDENT_REVIEW",
    },
    "HB-BLK-EXT-007": {
        "INDEPENDENCE_ATTESTATION", "REPRODUCTION_BUNDLE", "CROSS_ENVIRONMENT_COMPARISON", "INDEPENDENT_REVIEW",
    },
}
SEPARATION_KEYS = {
    "HB-BLK-CTRL-001": {"repository_admin_control", "independent_review_control"},
    "HB-BLK-EXT-001": {"author_control", "program_review_control", "security_review_control", "storage_review_control"},
    "HB-BLK-EXT-002": {"implementation_control", "legal_control", "program_review_control"},
    "HB-BLK-EXT-003": {"primary_oncall_control", "backup_oncall_control", "observer_control", "evidence_custody"},
    "HB-BLK-EXT-004": {"root_custody", "delegated_custody", "observer_custody", "transparency_custody"},
    "HB-BLK-EXT-005": {"raw_capture_acl", "implementation_acl", "sanitizer_control", "transfer_custody", "signing_root"},
    "HB-BLK-EXT-006": {
        "primary_runner_admin", "lab_runner_admin", "primary_artifact_custody", "lab_artifact_custody",
        "primary_signing_root", "lab_signing_root", "power_cut_control",
    },
    "HB-BLK-EXT-007": {
        "primary_credential_root", "reproduction_credential_root", "primary_runner_admin", "reproduction_runner_admin",
        "primary_cache_admin", "reproduction_cache_admin", "primary_artifact_custody", "reproduction_artifact_custody",
        "primary_signing_root", "reproduction_signing_root", "primary_network_egress", "reproduction_network_egress",
    },
}
UNEQUAL_SEPARATION_PAIRS = {
    "HB-BLK-CTRL-001": [("repository_admin_control", "independent_review_control")],
    "HB-BLK-EXT-001": [
        ("author_control", "program_review_control"), ("author_control", "security_review_control"),
        ("author_control", "storage_review_control"), ("program_review_control", "security_review_control"),
        ("program_review_control", "storage_review_control"), ("security_review_control", "storage_review_control"),
    ],
    "HB-BLK-EXT-002": [
        ("implementation_control", "legal_control"), ("implementation_control", "program_review_control"),
        ("legal_control", "program_review_control"),
    ],
    "HB-BLK-EXT-003": [
        ("primary_oncall_control", "backup_oncall_control"), ("primary_oncall_control", "observer_control"),
        ("backup_oncall_control", "observer_control"),
    ],
    "HB-BLK-EXT-004": [
        ("root_custody", "delegated_custody"), ("root_custody", "observer_custody"),
        ("root_custody", "transparency_custody"), ("delegated_custody", "observer_custody"),
        ("delegated_custody", "transparency_custody"), ("observer_custody", "transparency_custody"),
    ],
    "HB-BLK-EXT-005": [
        ("raw_capture_acl", "implementation_acl"), ("raw_capture_acl", "sanitizer_control"),
        ("implementation_acl", "transfer_custody"), ("sanitizer_control", "transfer_custody"),
    ],
    "HB-BLK-EXT-006": [
        ("primary_runner_admin", "lab_runner_admin"),
        ("primary_artifact_custody", "lab_artifact_custody"),
        ("primary_signing_root", "lab_signing_root"),
    ],
    "HB-BLK-EXT-007": [
        ("primary_credential_root", "reproduction_credential_root"),
        ("primary_runner_admin", "reproduction_runner_admin"),
        ("primary_cache_admin", "reproduction_cache_admin"),
        ("primary_artifact_custody", "reproduction_artifact_custody"),
        ("primary_signing_root", "reproduction_signing_root"),
        ("primary_network_egress", "reproduction_network_egress"),
    ],
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
PLACEHOLDERS = {"todo", "tbd", "unknown", "unexecuted", "placeholder", "example", "none", "n/a"}
SIGNATURE_METADATA_FIELDS = (
    "signer_id", "role", "key_id", "algorithm", "signed_at", "expires_at", "trust_root_id",
    "transparency_checkpoint_digest", "revocation_evidence_digest",
)
SignatureVerifier = Callable[[dict[str, Any], dict[str, Any], bytes], bool]


def fail(message: str) -> None:
    raise ValueError(message)


def non_placeholder(value: Any, field: str) -> str:
    if not isinstance(value, str) or len(value.strip()) < 2:
        fail(f"{field}: missing")
    lowered = value.strip().lower()
    if lowered in PLACEHOLDERS or any(token in lowered for token in ("<", ">", "replace-me")):
        fail(f"{field}: placeholder")
    return value.strip()


def parse_time(value: Any, field: str) -> datetime:
    if not isinstance(value, str):
        fail(f"{field}: string date-time required")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        fail(f"{field}: invalid date-time: {error}")
    if parsed.tzinfo is None:
        fail(f"{field}: timezone required")
    return parsed.astimezone(timezone.utc)


def schema_validator() -> Draft202012Validator:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema, format_checker=FormatChecker())


def validate_schema(data: dict[str, Any]) -> None:
    errors = sorted(schema_validator().iter_errors(data), key=lambda item: list(item.absolute_path))
    if errors:
        error = errors[0]
        location = ".".join(str(item) for item in error.absolute_path) or "$"
        fail(f"schema validation failed at {location}: {error.message}")


def signing_payload(data: dict[str, Any], signature: dict[str, Any]) -> bytes:
    envelope = copy.deepcopy(data)
    envelope["signatures"] = []
    metadata = {field: signature.get(field) for field in SIGNATURE_METADATA_FIELDS}
    document = {"domain": DOMAIN[:-1].decode("ascii"), "envelope": envelope, "signature_metadata": metadata}
    return DOMAIN + json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_digest(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def command_signature_verifier(command: Sequence[str]) -> SignatureVerifier:
    if not command:
        fail("signature verifier command missing")

    def verify(signature: dict[str, Any], actor: dict[str, Any], payload: bytes) -> bool:
        request = {
            "schema": "heptabao.signature-verification-request.v1",
            "payload_base64": base64.b64encode(payload).decode("ascii"),
            "payload_digest": sha256_digest(payload),
            "actor": actor,
            "signature": signature,
        }
        completed = subprocess.run(
            list(command), input=json.dumps(request, sort_keys=True), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if completed.returncode != 0:
            return False
        try:
            response = json.loads(completed.stdout)
        except json.JSONDecodeError:
            return False
        return response == {
            "verified": True,
            "signer_id": signature["signer_id"],
            "role": signature["role"],
            "organization": actor["organization"],
            "credential_id": actor["credential_id"],
            "credential_status": "CURRENT_SCOPE_BOUND",
            "key_id": signature["key_id"],
            "trust_root_id": signature["trust_root_id"],
            "payload_digest": signature["payload_digest"],
            "revocation_status": "CURRENT",
            "transparency_status": "INCLUDED",
        }

    return verify


def validate_envelope(
    data: dict[str, Any], *, require_closure: bool = False,
    expected_source: dict[str, str] | None = None, now: datetime | None = None,
    signature_verifier: SignatureVerifier | None = None,
) -> None:
    validate_schema(data)
    if data.get("schema") != SCHEMA_NAME:
        fail("schema mismatch")
    blocker = data.get("blocker_id")
    if blocker not in ALLOWED_BLOCKERS:
        fail("unsupported blocker")
    if data.get("repository") != {"id": REPOSITORY_ID, "full_name": REPOSITORY_FULL_NAME}:
        fail("repository identity mismatch")
    if data.get("claims") != {
        "qualification": False, "compatibility_claim": False, "selected_candidates": [],
        "selection_effect": "NONE", "production_authority": False, "migration_authority": False,
        "release_authority": False, "authority_effect": "NONE",
    }:
        fail("authority drift")
    if not require_closure:
        return
    if data.get("state") != "ACCEPTED":
        fail("closure requires ACCEPTED")
    if expected_source is None:
        fail("closure requires caller-supplied exact source expectations")
    source = data["source"]
    source_keys = (
        "commit", "tree", "base_commit", "merge_commit", "merge_tree",
        "merge_parent_one", "merge_parent_two", "plan_digest", "manifest_digest",
    )
    if set(expected_source) != set(source_keys):
        fail("expected source must contain every exact identity and digest")
    for key in source_keys:
        value = source.get(key)
        pattern = DIGEST if key.endswith("_digest") else HEX40
        if not isinstance(value, str) or not pattern.fullmatch(value):
            fail(f"source.{key}: exact value required")
        if value != expected_source[key]:
            fail(f"source.{key}: expected-source mismatch")
    if source["merge_parent_one"] != source["base_commit"] or source["merge_parent_two"] != source["commit"]:
        fail("merge parent declaration mismatch")
    if source["merge_commit"] in {source["commit"], source["base_commit"]}:
        fail("merge identity must be distinct from both parents")

    scope = data["scope"]
    if not scope or len(scope) != len(set(scope)):
        fail("closure scope must be non-empty and unique")
    for index, value in enumerate(scope):
        non_placeholder(value, f"scope[{index}]")

    current = now or datetime.now(timezone.utc)
    actors = data["actors"]
    roles: dict[str, dict[str, Any]] = {}
    actor_ids: set[str] = set()
    credential_ids: set[str] = set()
    for index, actor in enumerate(actors):
        stable_id = non_placeholder(actor.get("stable_id"), f"actors[{index}].stable_id")
        role = non_placeholder(actor.get("role"), f"actors[{index}].role")
        non_placeholder(actor.get("organization"), f"actors[{index}].organization")
        credential_id = non_placeholder(actor.get("credential_id"), f"actors[{index}].credential_id")
        non_placeholder(actor.get("credential_issuer"), f"actors[{index}].credential_issuer")
        non_placeholder(actor.get("revocation_authority"), f"actors[{index}].revocation_authority")
        credential_not_before = parse_time(
            actor.get("credential_not_before"), f"actors[{index}].credential_not_before"
        )
        credential_not_after = parse_time(
            actor.get("credential_not_after"), f"actors[{index}].credential_not_after"
        )
        if credential_not_before > current or credential_not_after <= current or credential_not_after <= credential_not_before:
            fail(f"actors[{index}]: accountable credential is not current")
        if actor.get("conflicts") != []:
            fail(f"{role}: unresolved conflicts")
        if stable_id in actor_ids:
            fail("actor identities must be distinct")
        if credential_id in credential_ids:
            fail("actor credential identities must be distinct")
        if role in roles:
            fail("actor roles must be unique")
        actor_ids.add(stable_id)
        credential_ids.add(credential_id)
        roles[role] = actor
        if role in INDEPENDENT_ROLES and actor.get("independent") is not True:
            fail(f"{role}: independence not affirmed")
    missing_roles = REQUIRED_ROLES[blocker] - set(roles)
    if missing_roles:
        fail(f"missing roles: {sorted(missing_roles)}")

    separation = data["separation"]
    expected_separation = SEPARATION_KEYS[blocker]
    if set(separation) != expected_separation:
        fail(f"separation key mismatch: expected {sorted(expected_separation)}")
    for key in sorted(expected_separation):
        non_placeholder(separation[key], f"separation.{key}")
    for left, right in UNEQUAL_SEPARATION_PAIRS[blocker]:
        if separation[left] == separation[right]:
            fail(f"shared control prohibited: {left} == {right}")

    checks = data["checks"]
    case_ids: set[str] = set()
    for index, check in enumerate(checks):
        case_id = non_placeholder(check.get("case_id"), f"checks[{index}].case_id")
        if case_id in case_ids:
            fail("duplicate check case")
        case_ids.add(case_id)
        if check.get("status") != "PASS":
            fail(f"{case_id}: non-PASS status")
        if not isinstance(check.get("evidence_digest"), str) or not DIGEST.fullmatch(check["evidence_digest"]):
            fail(f"{case_id}: evidence digest missing")
    missing_cases = REQUIRED_CASES[blocker] - case_ids
    if missing_cases:
        fail(f"required cases missing: {sorted(missing_cases)}")

    artifacts = data["artifacts"]
    artifact_kinds: set[str] = set()
    for index, artifact in enumerate(artifacts):
        kind = non_placeholder(artifact.get("kind"), f"artifacts[{index}].kind")
        if kind in artifact_kinds:
            fail("duplicate artifact kind")
        artifact_kinds.add(kind)
        non_placeholder(artifact.get("name"), f"artifacts[{index}].name")
        if not isinstance(artifact.get("digest"), str) or not DIGEST.fullmatch(artifact["digest"]):
            fail(f"artifacts[{index}].digest invalid")
        custody = non_placeholder(artifact.get("custody_uri"), f"artifacts[{index}].custody_uri")
        if not (custody.startswith("urn:") or custody.startswith("https://")):
            fail(f"artifacts[{index}].custody_uri must be an absolute URN or HTTPS URI")
    missing_artifacts = REQUIRED_ARTIFACT_KINDS[blocker] - artifact_kinds
    if missing_artifacts:
        fail(f"required artifact kinds missing: {sorted(missing_artifacts)}")

    finding_ids: set[str] = set()
    for finding in data["findings"]:
        finding_id = non_placeholder(finding.get("id"), "findings.id")
        if finding_id in finding_ids:
            fail("duplicate finding id")
        finding_ids.add(finding_id)
        if finding.get("severity") in {"CRITICAL", "HIGH", "UNCLASSIFIED"} and finding.get("state") != "CLOSED":
            fail("critical/high/unclassified finding remains open")

    if signature_verifier is None:
        fail("closure requires an external cryptographic signature verifier")
    signatures = data["signatures"]
    signed_ids: set[str] = set()
    signed_roles: set[str] = set()
    key_ids: set[str] = set()
    for index, signature in enumerate(signatures):
        signer_id = non_placeholder(signature.get("signer_id"), f"signatures[{index}].signer_id")
        role = non_placeholder(signature.get("role"), f"signatures[{index}].role")
        key_id = non_placeholder(signature.get("key_id"), f"signatures[{index}].key_id")
        algorithm = non_placeholder(signature.get("algorithm"), f"signatures[{index}].algorithm")
        if any(token in algorithm.lower() for token in ("test", "mock", "example")):
            fail("test/mock/example signature algorithm prohibited in closure mode")
        if signer_id in signed_ids or role in signed_roles or key_id in key_ids:
            fail("signer identities, roles and keys must be distinct")
        signed_ids.add(signer_id); signed_roles.add(role); key_ids.add(key_id)
        actor = roles.get(role)
        if actor is None or actor["stable_id"] != signer_id:
            fail("signature signer and role must bind to one declared actor")
        for field in ("trust_root_id", "signature"):
            non_placeholder(signature.get(field), f"signatures[{index}].{field}")
        for field in ("transparency_checkpoint_digest", "revocation_evidence_digest", "payload_digest"):
            value = signature.get(field)
            if not isinstance(value, str) or not DIGEST.fullmatch(value):
                fail(f"signatures[{index}].{field}: exact digest required")
        signed_at = parse_time(signature.get("signed_at"), f"signatures[{index}].signed_at")
        expires_at = parse_time(signature.get("expires_at"), f"signatures[{index}].expires_at")
        if signed_at > current or expires_at <= current or expires_at <= signed_at:
            fail("signature freshness invalid")
        payload = signing_payload(data, signature)
        if signature["payload_digest"] != sha256_digest(payload):
            fail("signature payload digest mismatch")
        if not signature_verifier(signature, actor, payload):
            fail("external cryptographic signature and accountable-role verification failed")
    missing_signatures = REQUIRED_ROLES[blocker] - signed_roles
    if missing_signatures:
        fail(f"required role signatures missing: {sorted(missing_signatures)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--require-closure", action="store_true")
    for field in (
        "commit", "tree", "base-commit", "merge-commit", "merge-tree",
        "merge-parent-one", "merge-parent-two", "plan-digest", "manifest-digest",
    ):
        parser.add_argument(f"--expected-{field}")
    parser.add_argument("--signature-verifier")
    parser.add_argument("--signature-verifier-arg", action="append", default=[])
    args = parser.parse_args()
    expected = None
    verifier = None
    if args.require_closure:
        expected = {
            "commit": args.expected_commit, "tree": args.expected_tree,
            "base_commit": args.expected_base_commit, "merge_commit": args.expected_merge_commit,
            "merge_tree": args.expected_merge_tree, "merge_parent_one": args.expected_merge_parent_one,
            "merge_parent_two": args.expected_merge_parent_two, "plan_digest": args.expected_plan_digest,
            "manifest_digest": args.expected_manifest_digest,
        }
        if any(value is None for value in expected.values()):
            parser.error("all expected source identities and digests are required with --require-closure")
        if not args.signature_verifier:
            parser.error("--signature-verifier is required with --require-closure")
        verifier = command_signature_verifier([args.signature_verifier, *args.signature_verifier_arg])
    for raw_path in args.paths:
        path = Path(raw_path)
        value = json.loads(path.read_text(encoding="utf-8"))
        validate_envelope(value, require_closure=args.require_closure, expected_source=expected, signature_verifier=verifier)
        print(f"PASS {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
