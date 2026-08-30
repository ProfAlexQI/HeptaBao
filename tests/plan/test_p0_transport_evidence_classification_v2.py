from __future__ import annotations

import copy
import importlib.util
import unittest
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load(name: str, relative: str):
    path = ROOT / relative
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


CLASSIFIER = load(
    "classify_p0_transport_evidence_v1",
    "scripts/classify_p0_transport_evidence_v1.py",
)
VALIDATOR = load(
    "validate_p0_transport_evidence_v2",
    "scripts/validate_p0_transport_evidence_v2.py",
)


def raw_report() -> dict:
    return {
        "schema": "heptabao.p0-transport-exact-result.v1",
        "source": {"repository": "ProfHepta/HeptaBao", "commit": "a" * 40},
        "result": "PASS",
        "counts": {"pass": 14, "fail": 0, "blocked": 0, "unexecuted": 0},
        "cases": [
            {"case_id": case_id, "status": "PASS", "evidence": {}}
            for case_id in sorted(CLASSIFIER.EXPECTED_CASES)
        ],
        "qualification": False,
        "compatibility_claim": False,
        "authority_effect": "NONE",
    }


class P0TransportEvidenceClassificationTests(unittest.TestCase):
    def test_complete_raw_result_is_classified_and_validated(self) -> None:
        result = CLASSIFIER.classify(raw_report())
        VALIDATOR.validate(
            result,
            expected_commit="a" * 40,
            expected_repository="ProfHepta/HeptaBao",
        )
        self.assertEqual(result["counts"]["executed_pass"], 11)
        self.assertEqual(result["counts"]["source_bound_pass"], 2)
        self.assertEqual(result["counts"]["best_effort_source_bound_pass"], 1)

    def test_source_bound_case_cannot_be_relabelled_as_runtime(self) -> None:
        result = CLASSIFIER.classify(raw_report())
        case = next(
            entry
            for entry in result["cases"]
            if entry["case_id"] == "P0-TRANSPORT-012"
        )
        case["evidence_class"] = "RUNTIME_SOCKET_OBSERVED"
        case["execution_status"] = "EXECUTED_PASS"
        with self.assertRaises(VALIDATOR.EvidenceValidationError):
            VALIDATOR.validate(result)

    def test_missing_case_fails_closed(self) -> None:
        raw = raw_report()
        raw["cases"] = raw["cases"][:-1]
        with self.assertRaises(CLASSIFIER.ClassificationError):
            CLASSIFIER.classify(raw)

    def test_authority_or_qualification_drift_fails_closed(self) -> None:
        result = CLASSIFIER.classify(raw_report())
        for field, value in (("qualification", True), ("authority_effect", "PRODUCTION")):
            mutated = copy.deepcopy(result)
            mutated[field] = value
            with self.assertRaises(VALIDATOR.EvidenceValidationError):
                VALIDATOR.validate(mutated)

    def test_runtime_count_cannot_be_inflated_to_fourteen(self) -> None:
        result = CLASSIFIER.classify(raw_report())
        result["counts"]["executed_pass"] = 14
        with self.assertRaises(VALIDATOR.EvidenceValidationError):
            VALIDATOR.validate(result)


if __name__ == "__main__":
    unittest.main()
