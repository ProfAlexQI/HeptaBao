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


class PlanV131Tests(unittest.TestCase):
    def test_checked_in_v1_3_1_contract_passes(self) -> None:
        MODULE.validate(ROOT)

    def test_external_blocker_cannot_be_self_closed(self) -> None:
        status_path = ROOT / "planning" / "HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
        status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(status)
        mutated["external_open"][0]["state"] = "CLOSED"

        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            required = [
                "crates/heptabao-p0-server/src/main.rs",
                "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
                "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
                "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md",
                "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md",
                "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
                ".github/workflows/plan-v1.3-gap-closure.yml",
            ]
            for relative in required:
                source = ROOT / relative
                destination = target_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            destination = target_root / "planning" / "HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)

    def test_authority_drift_is_rejected(self) -> None:
        status_path = ROOT / "planning" / "HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
        status = yaml.safe_load(status_path.read_text(encoding="utf-8"))
        mutated = copy.deepcopy(status)
        mutated["claims"]["production_authority"] = True

        with tempfile.TemporaryDirectory() as temporary:
            target_root = Path(temporary)
            required = [
                "crates/heptabao-p0-server/src/main.rs",
                "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
                "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
                "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md",
                "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md",
                "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
                ".github/workflows/plan-v1.3-gap-closure.yml",
            ]
            for relative in required:
                source = ROOT / relative
                destination = target_root / relative
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(source.read_bytes())
            destination = target_root / "planning" / "HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(yaml.safe_dump(mutated, sort_keys=False), encoding="utf-8")
            with self.assertRaises(MODULE.ValidationError):
                MODULE.validate(target_root)


if __name__ == "__main__":
    unittest.main()
