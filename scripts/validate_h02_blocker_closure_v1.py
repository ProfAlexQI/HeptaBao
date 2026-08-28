#!/usr/bin/env python3
"""Validate the H02 OS, durable-WAL and clock blocker-closure package."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / "planning/HEPTABAO_H02_OS_DURABLE_CLOCK_BLOCKER_CLOSURE_V1.yaml"
MANIFEST_PATH = ROOT / "probes/h02/openraft-tokio/Cargo.toml"
WORKFLOW_PATH = ROOT / ".github/workflows/h02-openraft-blocker-closure.yml"
RESULT_SCHEMA_PATH = ROOT / "schemas/heptabao_h02_blocker_closure_result_v1.schema.json"
EVIDENCE_SCHEMA_PATH = ROOT / "schemas/heptabao_h02_blocker_closure_evidence_v1.schema.json"

REQUIRED_FILES = [
    PLAN_PATH,
    MANIFEST_PATH,
    WORKFLOW_PATH,
    RESULT_SCHEMA_PATH,
    EVIDENCE_SCHEMA_PATH,
    ROOT / "scripts/h02_blocker_closure_evidence_v1.py",
    ROOT / "tests/platform/test_h02_blocker_closure_evidence_v1.py",
    ROOT / "probes/h02/openraft-tokio/src/bin/blocker_closure_lab.rs",
    ROOT / "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/durable.rs",
    ROOT / "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/os_clock.rs",
    ROOT / "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/os_clock_cluster.rs",
]


class ValidationFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise ValidationFailure(message)


def load_yaml(path: Path) -> dict:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)}: expected mapping")
    return value


def load_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        fail(f"{path.relative_to(ROOT)}: expected object")
    return value


def validate_plan() -> None:
    plan = load_yaml(PLAN_PATH)
    if plan.get("schema") != "heptabao.h02-os-durable-clock-blocker-closure.v1":
        fail("unexpected blocker-closure plan schema")
    if plan.get("plan_id") != "HEPTABAO-PLAN-2026-08-28" or str(plan.get("revision")) != "1.1":
        fail("plan identity drift")
    if plan.get("qualification") is not False or plan.get("selection_effect") != "NONE" or plan.get("authority_effect") != "NONE":
        fail("plan grants qualification, selection or authority")
    matrix = plan.get("execution_matrix", {})
    if matrix.get("toolchains") != ["1.85.0", "1.98.0"]:
        fail("toolchain matrix drift")
    if len(matrix.get("seeds", [])) != 3 or matrix.get("entries") != 6:
        fail("seed matrix must contain six entries")
    if matrix.get("scheduling") != "SERIAL_ON_ONE_RUNNER":
        fail("blocker closure matrix must be serialized")
    gaps = plan.get("remaining_external_gaps")
    if not isinstance(gaps, list) or len(gaps) < 5:
        fail("remaining external gaps are not explicit")


def validate_manifest() -> None:
    text = MANIFEST_PATH.read_text(encoding="utf-8")
    required = [
        'name = "heptabao-h02-openraft-blocker-closure-lab"',
        'path = "src/bin/blocker_closure_lab.rs"',
        'openraft = { version = "=0.10.0-alpha.33"',
        'features = ["serde", "tokio-rt", "type-alias"]',
        'tokio = { version = "=1.53.1"',
        '"process"',
    ]
    for marker in required:
        if marker not in text:
            fail(f"probe manifest missing marker: {marker}")


def validate_workflow() -> None:
    workflow = load_yaml(WORKFLOW_PATH)
    jobs = workflow.get("jobs", {})
    if set(jobs) != {"validate-plan", "closure-sequential", "authority-sentinel"}:
        fail(f"unexpected workflow jobs: {sorted(jobs)}")
    sequential = jobs["closure-sequential"]
    if "strategy" in sequential:
        fail("closure workflow must not fan out a runner-starving matrix")
    env = sequential.get("env", {})
    if env.get("TOOLCHAINS") != "1.85.0 1.98.0":
        fail("workflow toolchain list drift")
    if len(str(env.get("SEEDS", "")).split()) != 3:
        fail("workflow seed list drift")
    workflow_text = WORKFLOW_PATH.read_text(encoding="utf-8")
    for marker in (
        "heptabao-h02-openraft-blocker-closure-lab",
        "h02_blocker_closure_evidence_v1.py",
        "heptabao_h02_blocker_closure_result_v1.schema.json",
        "heptabao_h02_blocker_closure_evidence_v1.schema.json",
        "qualification",
        "authority_effect",
    ):
        if marker not in workflow_text:
            fail(f"workflow missing marker: {marker}")


def validate_schemas() -> None:
    result_schema = load_json(RESULT_SCHEMA_PATH)
    evidence_schema = load_json(EVIDENCE_SCHEMA_PATH)
    Draft202012Validator.check_schema(result_schema)
    Draft202012Validator.check_schema(evidence_schema)
    if result_schema.get("properties", {}).get("qualification", {}).get("const") is not False:
        fail("raw result schema does not force qualification=false")
    if evidence_schema.get("properties", {}).get("authority_effect", {}).get("const") != "NONE":
        fail("evidence schema does not force authority_effect=NONE")


def main() -> int:
    try:
        missing = [str(path.relative_to(ROOT)) for path in REQUIRED_FILES if not path.is_file()]
        if missing:
            fail(f"missing blocker closure files: {missing}")
        validate_plan()
        validate_manifest()
        validate_workflow()
        validate_schemas()
    except (ValidationFailure, OSError, ValueError, json.JSONDecodeError, yaml.YAMLError) as error:
        print(f"H02 blocker closure validation FAILED: {error}", file=sys.stderr)
        return 1
    print("H02 blocker closure validation passed: OS suspend + durable WAL + clock cases, six serialized entries, authority NONE")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
