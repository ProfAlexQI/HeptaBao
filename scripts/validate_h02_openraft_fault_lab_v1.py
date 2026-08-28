#!/usr/bin/env python3
"""Semantic validation for the H02 OpenRaft hostile-fault and linearizability slice."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "planning/HEPTABAO_H02_OPENRAFT_HOSTILE_FAULTS_LINEARIZABILITY_V1.yaml"
QUEUE = ROOT / "planning/HEPTABAO_H02_EXECUTION_QUEUE_V3.yaml"
MANIFEST = ROOT / "probes/h02/openraft-tokio/Cargo.toml"
MAIN = ROOT / "probes/h02/openraft-tokio/src/bin/openraft_fault_lab.rs"
CLUSTER = ROOT / "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/cluster.rs"
NETWORK = ROOT / "probes/h02/openraft-tokio/src/bin/inmemory_cluster/network.rs"
CHECKER = ROOT / "scripts/h02_linearizability_checker_v1.py"
COLLECTOR = ROOT / "scripts/h02_openraft_fault_lab_evidence_v1.py"
WORKFLOW = ROOT / ".github/workflows/h02-openraft-fault-lab.yml"
SCHEMAS = [
    ROOT / "schemas/heptabao_h02_linearizability_history_v1.schema.json",
    ROOT / "schemas/heptabao_h02_linearizability_result_v1.schema.json",
    ROOT / "schemas/heptabao_h02_openraft_hostile_snapshot_result_v1.schema.json",
    ROOT / "schemas/heptabao_h02_openraft_fault_lab_evidence_v1.schema.json",
]
TESTS = [
    ROOT / "tests/platform/test_h02_linearizability_checker_v1.py",
    ROOT / "tests/platform/test_h02_openraft_fault_lab_evidence_v1.py",
]


class Failure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: expected mapping")
    return value


def load_schema(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: expected object")
    Draft202012Validator.check_schema(value)
    return value


def main() -> int:
    try:
        required = [PLAN, QUEUE, MANIFEST, MAIN, CLUSTER, NETWORK, CHECKER, COLLECTOR, WORKFLOW, *SCHEMAS, *TESTS]
        for path in required:
            require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")

        plan = load_yaml(PLAN)
        require(plan["revision"] == "1.2", "plan revision mismatch")
        require(
            plan["status"] == "IMPLEMENTED_LOCALLY_VALIDATED_REMOTE_UNEXECUTED_NOT_QUALIFIED",
            "plan status must remain locally validated and remotely unexecuted",
        )
        require(plan["qualification"] is False, "plan cannot self-qualify")
        require(plan["selection_effect"] == "NONE", "selection effect must remain NONE")
        require(plan["authority_effect"] == "NONE", "authority effect must remain NONE")
        require(plan["stack"]["parent_pr"] == 22, "stack parent PR mismatch")
        require(plan["execution_matrix"]["entries"] == 6, "expected 2 toolchains x 3 seeds")
        require(plan["execution_matrix"]["remote_executions"] == 0, "remote execution count must begin at zero")
        require(plan["local_validation"]["total_python_tests"]["passed"] == 27, "expected 27 local Python tests")
        require(plan["local_validation"]["rust_compile"].startswith("UNEXECUTED_"), "Rust cannot be represented as executed")
        require(len(plan["promotion_blockers"]) >= 8, "promotion blocker set is too shallow")
        require(all(value is False for value in plan["authority_flags"].values()), "all authority flags must be false")

        queue = load_yaml(QUEUE)
        require(queue["status"] == "ACTIVE_FAIL_CLOSED", "queue must remain active and fail closed")
        require(queue["authority_effect"] == queue["selection_effect"] == "NONE", "queue authority must remain NONE")
        require(queue["runner_observation"]["classification"] == "INFRASTRUCTURE_UNEXECUTED", "runner state mismatch")
        require(queue["runner_observation"]["steps"] == [], "unexecuted runner must have no steps")

        manifest = MANIFEST.read_text(encoding="utf-8")
        for token in [
            'name = "heptabao-h02-openraft-fault-lab"',
            'path = "src/bin/openraft_fault_lab.rs"',
            'openraft = { version = "=0.10.0-alpha.33"',
            'openraft-memstore = { version = "=0.10.0-alpha.33"',
            'tokio = { version = "=1.53.1"',
            '"process"',
        ]:
            require(token in manifest, f"manifest binding missing: {token}")
        require("git =" not in manifest, "probe may not use mutable git candidate dependencies")

        source = "\n".join([MAIN.read_text(encoding="utf-8"), CLUSTER.read_text(encoding="utf-8"), NETWORK.read_text(encoding="utf-8")])
        for token in [
            "hostile-snapshot-child",
            "ABOUT_TO_INSTALL_STALE_COMMITTED_SNAPSHOT",
            "current_exe",
            "kill_on_drop",
            "install_full_snapshot",
            "snapshot.meta.last_log_id",
            "get_snapshot",
            "tokio::spawn",
            "ensure_linearizable(ReadPolicy::ReadIndex)",
            "REAL_OPENRAFT_READINDEX_SINGLE_REGISTER_HISTORY",
            "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
            "RaftNetworkFactory<TypeConfig>",
            "RaftNetworkV2<TypeConfig>",
        ]:
            require(token in source, f"fault-lab source token missing: {token}")
        for marker in ["PRIVATE KEY", "root_token", "unseal_share"]:
            require(marker not in source, f"secret marker in source: {marker}")

        checker = CHECKER.read_text(encoding="utf-8")
        for token in [
            "bounded-real-time-precedence-backtracking",
            "MAX_OPERATIONS = 64",
            'earlier["complete"] < later["invoke"]',
            "qualification must remain false",
            "selection_effect must remain NONE",
            "authority_effect must remain NONE",
        ]:
            require(token in checker, f"checker token missing: {token}")

        collector = COLLECTOR.read_text(encoding="utf-8")
        for token in [
            "linearizability result is not bound to the supplied history",
            "hostile result/exit-code mismatch",
            "Rust build/test phase did not succeed",
            "history generator did not execute successfully",
            "source tree is not clean",
            "BLOCK_PENDING_DURABLE_STORE_OS_DISK_CLOCK_AND_INDEPENDENT_REPRODUCTION",
        ]:
            require(token in collector, f"collector token missing: {token}")

        schemas = [load_schema(path) for path in SCHEMAS]
        for schema in schemas:
            properties = schema.get("properties", {})
            require(properties.get("qualification", {}).get("const") is False, "schema qualification must be false")
            require(properties.get("authority_effect", {}).get("const") == "NONE", "schema authority must be NONE")
        require(schemas[-1]["properties"]["promotion_effect"]["const"].startswith("BLOCK_"), "combined evidence promotion must remain blocked")

        for path in [CHECKER, COLLECTOR, *TESTS]:
            compile(path.read_text(encoding="utf-8"), str(path), "exec")

        workflow = WORKFLOW.read_text(encoding="utf-8")
        for token in [
            "1.85.0", "1.98.0", "0x5eed20260828cafe", "0x8badf00d12345678", "0xd15ea5e5cafef00d",
            "fail-fast: false", "hostile-snapshot-parent", "linearizability-history",
            "h02_linearizability_checker_v1.py", "h02_openraft_fault_lab_evidence_v1.py",
            "if: ${{ always() }}", "qualification=false", "authority=NONE",
        ]:
            require(token in workflow, f"workflow token missing: {token}")

        print("H02 OpenRaft hostile-fault/linearizability validation passed: 27 local Python tests declared; Rust executions=0; authority=NONE")
        return 0
    except (Failure, OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, KeyError) as exc:
        print(f"H02 OpenRaft hostile-fault/linearizability validation FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
