#!/usr/bin/env python3
"""Validate classified P0 transport evidence and its exact-source binding."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from classify_p0_transport_evidence_v1 import (
    BEST_EFFORT_SOURCE_BOUND,
    CLASS_BY_CASE,
    EXACT_HEAD_COMPILED_SOURCE_BOUND,
    EXPECTED_CASES,
    RUNTIME_OBSERVED,
    STATUS_BY_CLASS,
)


class EvidenceValidationError(RuntimeError):
    """Raised when classified evidence is incomplete or overclaims execution."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise EvidenceValidationError(message)


def validate(
    report: dict[str, Any],
    *,
    expected_commit: str | None = None,
    expected_repository: str | None = None,
) -> None:
    require(
        report.get("schema") == "heptabao.p0-transport-exact-result.v2",
        "classified schema drift",
    )
    require(report.get("result") == "PASS", "classified result must be PASS")
    require(
        report.get("evidence_result")
        == "PASS_WITH_EXPLICIT_EVIDENCE_CLASSIFICATION",
        "classified evidence result drift",
    )
    require(report.get("qualification") is False, "evidence cannot self-qualify")
    require(
        report.get("compatibility_claim") is False,
        "evidence cannot claim compatibility",
    )
    require(report.get("authority_effect") == "NONE", "authority effect drift")

    source = report.get("source")
    require(isinstance(source, dict), "source binding missing")
    if expected_commit is not None:
        require(source.get("commit") == expected_commit, "source commit binding drift")
    if expected_repository is not None:
        require(
            source.get("repository") == expected_repository,
            "source repository binding drift",
        )

    cases = report.get("cases")
    require(isinstance(cases, list), "classified cases missing")
    by_id = {
        case.get("case_id"): case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("case_id"), str)
    }
    require(len(by_id) == len(cases), "classified case IDs are missing or duplicated")
    require(set(by_id) == EXPECTED_CASES, "classified case coverage drift")
    for case_id, evidence_class in CLASS_BY_CASE.items():
        case = by_id[case_id]
        require(case.get("status") == "PASS", f"{case_id} bounded gate is not PASS")
        require(
            case.get("evidence_class") == evidence_class,
            f"{case_id} evidence class drift",
        )
        require(
            case.get("execution_status") == STATUS_BY_CLASS[evidence_class],
            f"{case_id} execution status overclaim",
        )

    counts = report.get("counts")
    require(
        counts
        == {
            "executed_pass": len(RUNTIME_OBSERVED),
            "source_bound_pass": len(EXACT_HEAD_COMPILED_SOURCE_BOUND),
            "best_effort_source_bound_pass": len(BEST_EFFORT_SOURCE_BOUND),
            "fail": 0,
            "blocked": 0,
            "unexecuted": 0,
            "total": len(EXPECTED_CASES),
        },
        "classified evidence counts drift",
    )
    require(counts["executed_pass"] == 11, "runtime pass count must be 11, not 14")

    model = report.get("evidence_model")
    require(isinstance(model, dict), "evidence model missing")
    require(
        model.get("runtime_observed_case_ids") == sorted(RUNTIME_OBSERVED),
        "runtime-observed set drift",
    )
    require(
        model.get("exact_head_compiled_source_bound_case_ids")
        == sorted(EXACT_HEAD_COMPILED_SOURCE_BOUND),
        "compiled source-bound set drift",
    )
    require(
        model.get("best_effort_source_bound_case_ids")
        == sorted(BEST_EFFORT_SOURCE_BOUND),
        "best-effort source-bound set drift",
    )
    require(
        model.get("source_presence_is_runtime_execution") is False,
        "source presence cannot be represented as runtime execution",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--expected-commit")
    parser.add_argument("--expected-repository")
    args = parser.parse_args()
    try:
        report = json.loads(args.input.read_text(encoding="utf-8"))
        require(isinstance(report, dict), "evidence must be one JSON object")
        validate(
            report,
            expected_commit=args.expected_commit,
            expected_repository=args.expected_repository,
        )
    except (OSError, json.JSONDecodeError, EvidenceValidationError) as error:
        print(f"P0 classified evidence validation FAILED: {error}")
        return 1
    print(
        "P0 classified evidence validation passed: executed=11 source-bound=2 "
        "best-effort-source-bound=1 qualification=false authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
