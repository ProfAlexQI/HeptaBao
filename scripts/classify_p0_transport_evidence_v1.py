#!/usr/bin/env python3
"""Classify exact-head P0 transport evidence without overstating runtime coverage."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

RUNTIME_OBSERVED = {
    "P0-TRANSPORT-001",
    "P0-TRANSPORT-002",
    "P0-TRANSPORT-003",
    "P0-TRANSPORT-004",
    "P0-TRANSPORT-005",
    "P0-TRANSPORT-006",
    "P0-TRANSPORT-007",
    "P0-TRANSPORT-008",
    "P0-TRANSPORT-009",
    "P0-TRANSPORT-010",
    "P0-TRANSPORT-013",
}
EXACT_HEAD_COMPILED_SOURCE_BOUND = {
    "P0-TRANSPORT-011",
    "P0-TRANSPORT-012",
}
BEST_EFFORT_SOURCE_BOUND = {"P0-TRANSPORT-014"}
EXPECTED_CASES = (
    RUNTIME_OBSERVED | EXACT_HEAD_COMPILED_SOURCE_BOUND | BEST_EFFORT_SOURCE_BOUND
)

CLASS_BY_CASE = {
    **{case_id: "RUNTIME_SOCKET_OBSERVED" for case_id in RUNTIME_OBSERVED},
    **{
        case_id: "EXACT_HEAD_COMPILED_SOURCE_BOUND"
        for case_id in EXACT_HEAD_COMPILED_SOURCE_BOUND
    },
    **{
        case_id: "BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND"
        for case_id in BEST_EFFORT_SOURCE_BOUND
    },
}
STATUS_BY_CLASS = {
    "RUNTIME_SOCKET_OBSERVED": "EXECUTED_PASS",
    "EXACT_HEAD_COMPILED_SOURCE_BOUND": "SOURCE_BOUND_PASS",
    "BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND": "SOURCE_BOUND_BEST_EFFORT_PASS",
}


class ClassificationError(RuntimeError):
    """Raised when raw evidence cannot be classified without ambiguity."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ClassificationError(message)


def classify(report: dict[str, Any]) -> dict[str, Any]:
    require(
        report.get("schema") == "heptabao.p0-transport-exact-result.v1",
        "raw P0 transport schema drift",
    )
    require(report.get("result") == "PASS", "raw P0 transport result is not PASS")
    require(report.get("qualification") is False, "raw result cannot self-qualify")
    require(
        report.get("compatibility_claim") is False,
        "raw result cannot claim compatibility",
    )
    require(report.get("authority_effect") == "NONE", "raw authority effect drift")

    cases = report.get("cases")
    require(isinstance(cases, list), "raw P0 transport cases missing")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    require(len(case_ids) == len(cases), "every raw case must be a mapping with case_id")
    require(len(case_ids) == len(set(case_ids)), "raw P0 transport case IDs are duplicated")
    require(set(case_ids) == EXPECTED_CASES, "raw P0 transport case coverage drift")

    classified_cases: list[dict[str, Any]] = []
    for raw_case in cases:
        case = dict(raw_case)
        case_id = case["case_id"]
        require(case.get("status") == "PASS", f"{case_id} did not pass its bounded gate")
        evidence_class = CLASS_BY_CASE[case_id]
        case["evidence_class"] = evidence_class
        case["execution_status"] = STATUS_BY_CLASS[evidence_class]
        classified_cases.append(case)

    result = dict(report)
    result["schema"] = "heptabao.p0-transport-exact-result.v2"
    result["cases"] = classified_cases
    result["raw_counts"] = report.get("counts")
    result["counts"] = {
        "executed_pass": len(RUNTIME_OBSERVED),
        "source_bound_pass": len(EXACT_HEAD_COMPILED_SOURCE_BOUND),
        "best_effort_source_bound_pass": len(BEST_EFFORT_SOURCE_BOUND),
        "fail": 0,
        "blocked": 0,
        "unexecuted": 0,
        "total": len(EXPECTED_CASES),
    }
    result["evidence_model"] = {
        "classification": "MIXED_RUNTIME_AND_EXACT_HEAD_SOURCE_BOUND",
        "runtime_observed_case_ids": sorted(RUNTIME_OBSERVED),
        "exact_head_compiled_source_bound_case_ids": sorted(
            EXACT_HEAD_COMPILED_SOURCE_BOUND
        ),
        "best_effort_source_bound_case_ids": sorted(BEST_EFFORT_SOURCE_BOUND),
        "runtime_transport_pass_count": len(RUNTIME_OBSERVED),
        "source_bound_pass_count": len(EXACT_HEAD_COMPILED_SOURCE_BOUND)
        + len(BEST_EFFORT_SOURCE_BOUND),
        "source_presence_is_runtime_execution": False,
    }
    result["result"] = "PASS"
    result["evidence_result"] = "PASS_WITH_EXPLICIT_EVIDENCE_CLASSIFICATION"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        raw = json.loads(args.input.read_text(encoding="utf-8"))
        require(isinstance(raw, dict), "raw result must be one JSON object")
        result = classify(raw)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
    except (OSError, json.JSONDecodeError, ClassificationError) as error:
        print(f"P0 transport evidence classification FAILED: {error}")
        return 1
    print(
        "P0 transport evidence classified: runtime=11 source-bound=2 "
        "best-effort-source-bound=1 authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
