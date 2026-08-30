from __future__ import annotations

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "scripts" / "validate_v1_3_1_final_closure_v1.py"
SPEC = importlib.util.spec_from_file_location("validate_v1_3_1_final_closure_v1", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)

SURFACE = [
    "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml",
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3_1.yaml",
    "docs/execution/HEPTABAO_V1_3_1_FINAL_CLOSURE_PROTOCOL.md",
    "scripts/classify_p0_transport_evidence_v1.py",
    "scripts/validate_p0_transport_evidence_v2.py",
    "scripts/validate_v1_3_1_final_closure_v1.py",
    "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs",
    ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml",
]


def copy_surface(target: Path) -> None:
    for relative in SURFACE:
        source = ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def replace(target: Path, relative: str, old: str, new: str) -> None:
    path = target / relative
    text = path.read_text(encoding="utf-8")
    if old not in text:
        raise AssertionError(f"missing mutation marker {old!r} in {relative}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


class V131FinalClosureTests(unittest.TestCase):
    def test_checked_in_final_closure_contract_passes(self) -> None:
        MODULE.validate(ROOT)

    def test_source_bound_case_cannot_be_declared_runtime(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            copy_surface(target)
            replace(
                target,
                "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
                "evidence_class: EXACT_HEAD_COMPILED_SOURCE_BOUND",
                "evidence_class: RUNTIME_SOCKET_OBSERVED",
            )
            with self.assertRaises(MODULE.FinalClosureValidationError):
                MODULE.validate(target)

    def test_merge_lane_cannot_checkout_the_head_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            copy_surface(target)
            replace(
                target,
                ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml",
                "matrix.source_kind == 'merge' && github.sha",
                "matrix.source_kind == 'merge' && github.event.pull_request.head.sha",
            )
            with self.assertRaises(MODULE.FinalClosureValidationError):
                MODULE.validate(target)

    def test_legacy_vote_equivalence_guard_is_required(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            copy_surface(target)
            replace(
                target,
                "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs",
                "let legacy_log_vote_matches = semantic_field_matches(",
                "let legacy_log_vote_check_removed = semantic_field_matches(",
            )
            with self.assertRaises(MODULE.FinalClosureValidationError):
                MODULE.validate(target)

    def test_external_blockers_cannot_be_removed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            copy_surface(target)
            path = target / "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["external_open"] = value["external_open"][:-1]
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            with self.assertRaises(MODULE.FinalClosureValidationError):
                MODULE.validate(target)

    def test_authority_drift_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary)
            copy_surface(target)
            path = target / "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml"
            value = yaml.safe_load(path.read_text(encoding="utf-8"))
            value["claims"]["production_authority"] = True
            path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
            with self.assertRaises(MODULE.FinalClosureValidationError):
                MODULE.validate(target)


if __name__ == "__main__":
    unittest.main()
