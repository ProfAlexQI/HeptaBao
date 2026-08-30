from __future__ import annotations

import copy
import importlib.util
import tempfile
import unittest
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_plan_v1_3_1.py"
SPEC = importlib.util.spec_from_file_location("validate_plan_v1_3_1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

STATUS_PATH = "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
REQUIRED_FILES = [
    "crates/heptabao-protocol/src/lib.rs",
    "crates/heptabao-authbus-contracts/src/lib.rs",
    "crates/heptabao-p0-server/src/lib.rs",
    "crates/heptabao-p0-server/src/main.rs",
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    "docs/protocol/HEPTABAO_H03_PROTOCOL_CONTRACT_V1.md",
    "docs/auth/HEPTABAO_AUTHBUS_INTEGRATION_CONTRACT_V1.md",
    "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md",
    "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md",
    "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    ".github/workflows/plan-v1.3-gap-closure.yml",
]


def copy_validation_surface(target_root: Path) -> None:
    for relative in REQUIRED_FILES + [STATUS_PATH]:
        source = ROOT / relative
        destination = target_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(source.read_bytes())


def mutate_text(target_root: Path, relative: str, old: str, new: str) -> None:
    path = target_root / relative
    source = path.read_text(encoding="utf-8")
    if old not in source:
        raise AssertionError(f"mutation marker not found in {relative}: {old}")
    path.write_text(source.replace(old, new, 1), encoding="utf-8")


class PlanV131Tests(unittest.TestCase):
    def test_checked_in_v1_3_1_contract_passes(self) -> None:
        MODULE.validate(ROOT)

    def test_external_blocker_cannot_be_self_closed(self) -> None:
        status_path = ROOT / STATUS_PATH
        status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(status)
        mutated["external_open"][0]["state"] = "CLOSED"

        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            destination = target_root / STATUS_PATH
            destination.write_text(
                yaml.safe_dump(mutated, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_authority_drift_is_rejected(self) -> None:
        status_path = ROOT / STATUS_PATH
        status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(status)
        mutated["claims"]["production_authority"] = True

        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            destination = target_root / STATUS_PATH
            destination.write_text(
                yaml.safe_dump(mutated, sort_keys=False),
                encoding="utf-8",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_infallible_worker_spawn_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/main.rs",
                "thread::Builder::new()",
                "thread::spawn(",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_unbounded_rejection_write_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/main.rs",
                "write_response_with_timeout",
                "write_response_without_deadline",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_invalid_deadline_guard_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-protocol/src/lib.rs",
                "self.deadline <= self.received_at",
                "self.deadline < self.received_at",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_request_body_drop_guard_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-protocol/src/lib.rs",
                "impl Drop for ParsedHttpRequest",
                "impl ParsedHttpRequest",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_response_body_drop_guard_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/lib.rs",
                "impl Drop for P0Response",
                "impl P0ResponseDropRemoved",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_server_state_debug_redaction_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/lib.rs",
                "impl fmt::Debug for ServerState",
                "impl ServerStateDebugRemoved",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_request_registry_debug_redaction_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/main.rs",
                "impl fmt::Debug for RequestIdRegistry",
                "impl RequestIdRegistryDebugRemoved",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_authbus_digest_preimage_clear_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-authbus-contracts/src/lib.rs",
                "canonical_request.fill(0)",
                "canonical_request.clear()",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_authbus_signature_payload_clear_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-authbus-contracts/src/lib.rs",
                "payload.fill(0)",
                "payload.clear()",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_raw_quote_rejection_guard_removal_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            copy_validation_surface(target_root)
            mutate_text(
                target_root,
                "crates/heptabao-p0-server/src/lib.rs",
                "|| byte == b'\"'",
                "",
            )
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)


if __name__ == "__main__":
    unittest.main()
