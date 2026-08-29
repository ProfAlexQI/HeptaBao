#!/usr/bin/env python3
"""Semantic validation for the OpenRaft in-memory cluster development slice."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "planning/HEPTABAO_H02_OPENRAFT_INMEMORY_CLUSTER_V1.yaml"
SCHEMA = ROOT / "schemas/heptabao_h02_openraft_cluster_evidence_v1.schema.json"
MANIFEST = ROOT / "probes/h02/openraft-tokio/Cargo.toml"
MAIN = ROOT / "probes/h02/openraft-tokio/src/bin/inmemory_cluster.rs"
CLUSTER = ROOT / "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs"
NETWORK = ROOT / "probes/h02/openraft-tokio/src/bin/inmemory_cluster/network.rs"
COLLECTOR = ROOT / "scripts/h02_openraft_inmemory_cluster_evidence_v1.py"
WORKFLOW = ROOT / ".github/workflows/h02-openraft-inmemory-cluster.yml"

REQUIRED_CASES = {
    "raft-deterministic-apply-and-restart",
    "raft-committed-snapshot-conflict-rejected",
    "raft-joint-membership-single-writer",
    "raft-process-pause-plus-partition",
    "raft-quorum-loss-fail-closed",
    "raft-incomplete-run-replay-diagnostics",
}


class Failure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise Failure(message)


def load_yaml(path: Path) -> dict[str, Any]:
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: expected mapping")
    return value


def main() -> int:
    try:
        for path in [PLAN, SCHEMA, MANIFEST, MAIN, CLUSTER, NETWORK, COLLECTOR, WORKFLOW]:
            require(path.is_file(), f"missing required file: {path.relative_to(ROOT)}")

        plan = load_yaml(PLAN)
        require(plan["status"] == "IMPLEMENTED_UNEXECUTED_NOT_QUALIFIED", "plan status must remain unexecuted")
        require(plan["qualification"] is False, "plan cannot self-qualify")
        require(plan["selection_effect"] == plan["authority_effect"] == "NONE", "authority must remain NONE")
        require(plan["execution_matrix"]["entries"] == 6, "expected 2 toolchains x 3 seeds")
        require(plan["execution_matrix"]["remote_executions"] == 0, "remote execution count must start at zero")
        require({item["case_id"] for item in plan["cases"]} == REQUIRED_CASES, "case set mismatch")
        require(len(plan["promotion_blockers"]) >= 8, "promotion blocker set is too shallow")

        manifest = MANIFEST.read_text(encoding="utf-8")
        required_manifest = [
            'default-run = "heptabao-h02-probe-openraft-tokio"',
            'name = "heptabao-h02-openraft-inmemory-cluster"',
            'openraft = { version = "=0.10.0-alpha.33"',
            'openraft-memstore = { version = "=0.10.0-alpha.33"',
            'tokio = { version = "=1.53.1"',
        ]
        for token in required_manifest:
            require(token in manifest, f"manifest binding missing: {token}")
        require("git =" not in manifest and 'path = "../../../' not in manifest, "probe may not use mutable git/path candidate source")

        source = "\n".join(
            [
                MAIN.read_text(encoding="utf-8"),
                CLUSTER.read_text(encoding="utf-8"),
                NETWORK.read_text(encoding="utf-8"),
            ]
        )
        required_source = [
            "RaftNetworkFactory<TypeConfig>",
            "RaftNetworkV2<TypeConfig>",
            "append_entries",
            "pre_vote",
            "full_snapshot",
            "install_full_snapshot",
            "Raft::<TypeConfig",
            "new_mem_store",
            ".initialize(",
            ".add_learner(",
            ".change_membership(",
            ".client_write(",
            ".ensure_linearizable(",
            ".trigger().snapshot()",
            ".shutdown().await",
            "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
        ]
        for token in required_source:
            require(token in source, f"real cluster source token missing: {token}")
        require('include_bytes!("../../../fixtures' not in source, "cluster probe must not embed secret fixtures")
        for marker in ["PRIVATE KEY", "root_token", "unseal_share"]:
            require(marker not in source, f"secret marker in source: {marker}")

        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
        require(schema["properties"]["qualification"]["const"] is False, "schema qualification must be false")
        require(schema["properties"]["authority_effect"]["const"] == "NONE", "schema authority must be NONE")
        require(schema["properties"]["promotion_effect"]["const"].startswith("BLOCK_"), "promotion must remain blocked")

        text = WORKFLOW.read_text(encoding="utf-8")
        for token in [
            "1.85.0",
            "1.98.0",
            "0x5eed20260828cafe",
            "0x8badf00d12345678",
            "0xd15ea5e5cafef00d",
            "Execute all six entries serially and retain every outcome",
            "exit 0",
            "if: ${{ always() }}",
        ]:
            require(token in text, f"workflow token missing: {token}")
        require("qualification=false" in text and "authority=NONE" in text, "workflow authority sentinel missing")

        print(
            "H02 OpenRaft in-memory cluster validation passed: "
            "real-network/store/FSM specified; executions=0; authority=NONE"
        )
        return 0
    except (Failure, OSError, ValueError, json.JSONDecodeError, yaml.YAMLError, KeyError) as exc:
        print(f"H02 OpenRaft in-memory cluster validation FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
