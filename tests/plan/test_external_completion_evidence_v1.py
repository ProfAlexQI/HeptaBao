from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "external_validator", ROOT / "scripts/validate_external_completion_evidence_v1.py"
)
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VALIDATOR)
DIGEST = "sha256:" + "a" * 64
EXPECTED = {
    "commit": "1" * 40,
    "tree": "2" * 40,
    "base_commit": "0" * 40,
    "merge_commit": "3" * 40,
    "merge_tree": "4" * 40,
    "merge_parent_one": "0" * 40,
    "merge_parent_two": "1" * 40,
    "plan_digest": "sha256:" + "b" * 64,
    "manifest_digest": "sha256:" + "c" * 64,
}
NOW = datetime(2026, 9, 2, tzinfo=timezone.utc)


def accepted_ext007() -> dict:
    roles = sorted(VALIDATOR.REQUIRED_ROLES["HB-BLK-EXT-007"])
    actors = [
        {
            "stable_id": f"actor-{index:03d}",
            "role": role,
            "organization": f"Independent Lab {index}",
            "independent": True,
            "conflicts": [],
            "credential_id": f"credential-{index:03d}",
            "credential_issuer": f"Independent Credential Authority {index}",
            "credential_not_before": "2026-09-01T00:00:00Z",
            "credential_not_after": "2027-09-01T00:00:00Z",
            "revocation_authority": f"urn:revocation:authority:{index:03d}",
        }
        for index, role in enumerate(roles, 1)
    ]
    separation = {
        "primary_credential_root": "urn:primary:credential-root",
        "reproduction_credential_root": "urn:reproduction:credential-root",
        "primary_runner_admin": "urn:primary:runner-admin",
        "reproduction_runner_admin": "urn:reproduction:runner-admin",
        "primary_cache_admin": "urn:primary:cache-admin",
        "reproduction_cache_admin": "urn:reproduction:cache-admin",
        "primary_artifact_custody": "urn:primary:artifact-custody",
        "reproduction_artifact_custody": "urn:reproduction:artifact-custody",
        "primary_signing_root": "urn:primary:signing-root",
        "reproduction_signing_root": "urn:reproduction:signing-root",
        "primary_network_egress": "urn:primary:network-egress",
        "reproduction_network_egress": "urn:reproduction:network-egress",
    }
    value = {
        "schema": "heptabao.external-completion-evidence.v1",
        "blocker_id": "HB-BLK-EXT-007",
        "state": "ACCEPTED",
        "repository": {"id": 1349115072, "full_name": "TrillionniumFoundation/HeptaBao"},
        "source": dict(EXPECTED),
        "scope": ["exact head and prospective merge full reproduction"],
        "actors": actors,
        "separation": separation,
        "checks": [
            {"case_id": case_id, "status": "PASS", "evidence_digest": DIGEST}
            for case_id in sorted(VALIDATOR.REQUIRED_CASES["HB-BLK-EXT-007"])
        ],
        "artifacts": [
            {
                "kind": kind,
                "name": kind.lower().replace("_", " "),
                "digest": DIGEST,
                "custody_uri": f"urn:lab:artifact:{kind.lower()}",
                "classification": "RESTRICTED_REFERENCE",
            }
            for kind in sorted(VALIDATOR.REQUIRED_ARTIFACT_KINDS["HB-BLK-EXT-007"])
        ],
        "findings": [],
        "signatures": [
            {
                "signer_id": actor["stable_id"],
                "role": actor["role"],
                "key_id": f"key-{index:03d}",
                "algorithm": "ed25519-profile-v1",
                "signed_at": "2026-09-01T00:00:00Z",
                "expires_at": "2027-09-01T00:00:00Z",
                "trust_root_id": f"trust-root-{index:03d}",
                "transparency_checkpoint_digest": "sha256:" + "d" * 64,
                "revocation_evidence_digest": "sha256:" + "e" * 64,
                "payload_digest": DIGEST,
                "signature": ("ab" if index == 1 else "cd") * 32,
            }
            for index, actor in enumerate(actors, 1)
        ],
        "claims": {
            "qualification": False,
            "compatibility_claim": False,
            "selected_candidates": [],
            "selection_effect": "NONE",
            "production_authority": False,
            "migration_authority": False,
            "release_authority": False,
            "authority_effect": "NONE",
        },
    }
    for signature in value["signatures"]:
        signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
    return value


def accepting_verifier(signature: dict, actor: dict, payload: bytes) -> bool:
    return (
        actor["stable_id"] == signature["signer_id"]
        and actor["role"] == signature["role"]
        and signature["payload_digest"] == VALIDATOR.sha256_digest(payload)
    )


class ExternalCompletionEvidenceTests(unittest.TestCase):
    def validate(self, value: dict, *, verifier=accepting_verifier) -> None:
        VALIDATOR.validate_envelope(
            value,
            require_closure=True,
            expected_source=EXPECTED,
            now=NOW,
            signature_verifier=verifier,
        )

    def test_bounded_valid_closure_envelope_passes_with_external_verifier(self) -> None:
        self.validate(accepted_ext007())

    def test_templates_are_schema_shaped_but_not_closure(self) -> None:
        for path in sorted((ROOT / "qualifications/external/templates").glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            VALIDATOR.validate_envelope(value, require_closure=False)
            with self.assertRaises(ValueError):
                self.validate(value)

    def test_self_asserted_validity_without_external_verifier_fails(self) -> None:
        value = accepted_ext007()
        with self.assertRaisesRegex(ValueError, "external cryptographic signature verifier"):
            self.validate(value, verifier=None)

    def test_schema_rejects_unknown_self_asserted_verification_field(self) -> None:
        value = accepted_ext007()
        value["signatures"][0]["verification"] = "VALID"
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            self.validate(value)

    def test_tampered_payload_fails_digest_binding(self) -> None:
        value = accepted_ext007()
        value["scope"].append("tampered scope")
        with self.assertRaisesRegex(ValueError, "payload digest mismatch"):
            self.validate(value)

    def test_external_verifier_rejection_fails_closed(self) -> None:
        with self.assertRaisesRegex(ValueError, "external cryptographic"):
            self.validate(accepted_ext007(), verifier=lambda _signature, _actor, _payload: False)

    def test_missing_required_case_fails_closed(self) -> None:
        value = accepted_ext007()
        value["checks"].pop()
        for signature in value["signatures"]:
            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
        with self.assertRaisesRegex(ValueError, "required cases missing"):
            self.validate(value)

    def test_missing_required_artifact_kind_fails_closed(self) -> None:
        value = accepted_ext007()
        value["artifacts"].pop()
        for signature in value["signatures"]:
            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
        with self.assertRaisesRegex(ValueError, "required artifact kinds missing"):
            self.validate(value)

    def test_non_pass_case_fails_closed(self) -> None:
        value = accepted_ext007()
        value["checks"][0]["status"] = "UNKNOWN"
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_shared_actor_identity_fails_closed(self) -> None:
        value = accepted_ext007()
        value["actors"][1]["stable_id"] = value["actors"][0]["stable_id"]
        with self.assertRaises(ValueError):
            self.validate(value)


    def test_actor_credential_is_schema_mandatory(self) -> None:
        value = accepted_ext007()
        del value["actors"][0]["credential_id"]
        with self.assertRaisesRegex(ValueError, "schema validation failed"):
            self.validate(value)

    def test_expired_actor_credential_fails_closed(self) -> None:
        value = accepted_ext007()
        value["actors"][0]["credential_not_after"] = "2026-09-01T00:00:00Z"
        for signature in value["signatures"]:
            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
        with self.assertRaisesRegex(ValueError, "accountable credential is not current"):
            self.validate(value)

    def test_duplicate_actor_credential_fails_closed(self) -> None:
        value = accepted_ext007()
        value["actors"][1]["credential_id"] = value["actors"][0]["credential_id"]
        for signature in value["signatures"]:
            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
        with self.assertRaisesRegex(ValueError, "credential identities must be distinct"):
            self.validate(value)

    def test_signature_must_bind_to_declared_actor_and_role(self) -> None:
        value = accepted_ext007()
        value["signatures"][0]["signer_id"] = "undeclared-signer"
        with self.assertRaisesRegex(ValueError, "declared actor"):
            self.validate(value)

    def test_shared_primary_and_reproduction_control_fails_closed(self) -> None:
        value = accepted_ext007()
        value["separation"]["reproduction_runner_admin"] = value["separation"]["primary_runner_admin"]
        for signature in value["signatures"]:
            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))
        with self.assertRaisesRegex(ValueError, "shared control prohibited"):
            self.validate(value)

    def test_source_or_parent_drift_fails_closed(self) -> None:
        for field in ("tree", "merge_parent_two"):
            value = accepted_ext007()
            value["source"][field] = "f" * 40
            with self.assertRaises(ValueError):
                self.validate(value)

    def test_expired_signature_fails_closed(self) -> None:
        value = accepted_ext007()
        value["signatures"][0]["expires_at"] = "2026-09-01T00:00:00Z"
        with self.assertRaises(ValueError):
            self.validate(value)

    def test_test_algorithm_fails_closed(self) -> None:
        value = accepted_ext007()
        value["signatures"][0]["algorithm"] = "test-ed25519-profile"
        value["signatures"][0]["payload_digest"] = VALIDATOR.sha256_digest(
            VALIDATOR.signing_payload(value, value["signatures"][0])
        )
        with self.assertRaisesRegex(ValueError, "test/mock/example"):
            self.validate(value)

    def test_authority_elevation_fails_closed(self) -> None:
        value = accepted_ext007()
        value["claims"]["production_authority"] = True
        with self.assertRaises(ValueError):
            self.validate(value)


if __name__ == "__main__":
    unittest.main()
