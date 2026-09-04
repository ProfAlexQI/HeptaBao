#!/usr/bin/env python3
"""Validate cumulative V1.4.7-V1.8 lineage after 42-crate materialization.

Historical validators and hostile tests are executed on their exact historical
source before each successor materializer. After V1.8 rewrites shared current
portals and module guides, re-running those exact-tree validators would create
false failures. This successor gate verifies the cumulative invariants without
rewriting historical evidence or interpreting an unmerged source stage as a
closure receipt.
"""
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path.cwd()
CLAIMS = {
    "qualification": False,
    "compatibility_claim": False,
    "selected_candidates": [],
    "selection_effect": "NONE",
    "production_authority": False,
    "migration_authority": False,
    "release_authority": False,
    "authority_effect": "NONE",
}
STAGES: tuple[dict[str, Any], ...] = (
    {
        "name": "V1.4.7",
        "status": "planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml",
        "blockers": "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml",
        "truth": "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml",
        "module_count": 19,
        "ids": [f"HB-BLK-REPO-{index:03d}" for index in range(59, 63)],
        "plan": "docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md",
    },
    {
        "name": "V1.5.0",
        "status": "planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml",
        "blockers": "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml",
        "truth": "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml",
        "module_count": 28,
        "ids": [f"HB-BLK-REPO-{index:03d}" for index in range(63, 72)],
        "plan": "docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md",
    },
    {
        "name": "V1.6.0",
        "status": "planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml",
        "blockers": "planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml",
        "truth": "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml",
        "module_count": 32,
        "ids": [f"HB-BLK-REPO-{index:03d}" for index in range(72, 79)],
        "plan": "docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md",
    },
    {
        "name": "V1.7.0",
        "status": "planning/HEPTABAO_V1_7_0_SERVICE_HA_STATUS.yaml",
        "blockers": "planning/HEPTABAO_BLOCKER_REGISTER_V1_7_0.yaml",
        "truth": "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_7_0.yaml",
        "module_count": 37,
        "ids": [f"HB-BLK-REPO-{index:03d}" for index in range(79, 86)],
        "plan": "docs/plan/HEPTABAO_PLAN_V1_7_0_SERVICE_HA_PLUGIN_COMPATIBILITY.md",
    },
    {
        "name": "V1.8.0",
        "status": "planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml",
        "blockers": "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml",
        "truth": "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml",
        "module_count": 42,
        "ids": [f"HB-BLK-REPO-{index:03d}" for index in range(86, 94)],
        "plan": "docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md",
    },
)
REQUIRED_V150 = {
    "heptabao-namespace", "heptabao-policy", "heptabao-identity",
    "heptabao-token", "heptabao-lease", "heptabao-system",
    "heptabao-plugin-contracts", "heptabao-kv", "heptabao-control-plane",
}
REQUIRED_V160 = {
    "heptabao-kms-contracts", "heptabao-runtime",
    "heptabao-recovery-providers", "heptabao-lifecycle-ops",
}
REQUIRED_V170 = {
    "heptabao-http-api", "heptabao-ha-core", "heptabao-plugin-host",
    "heptabao-compat-runner", "heptabao-client-tools",
}
REQUIRED_V180 = {
    "heptabao-config", "heptabao-observability", "heptabao-service",
    "heptabao-cluster", "heptabao-agent-proxy",
}


def load(relative: str) -> dict[str, Any]:
    path = ROOT / relative
    if not path.is_file():
        raise SystemExit(f"missing inherited stage object: {relative}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{relative}: expected mapping")
    return value


def workspace_names() -> set[str]:
    data = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            cargo = path / "Cargo.toml"
            if not cargo.is_file():
                continue
            name = tomllib.loads(cargo.read_text(encoding="utf-8"))["package"]["name"]
            if name in names:
                raise SystemExit(f"duplicate workspace package: {name}")
            names.add(name)
    return names


def verify_source_baseline(label: str, value: dict[str, Any]) -> None:
    baseline = value.get("source_baseline")
    if not isinstance(baseline, dict):
        raise SystemExit(f"{label}: missing source baseline")
    commit = baseline.get("commit")
    tree = baseline.get("tree")
    if not isinstance(commit, str) or len(commit) != 40:
        raise SystemExit(f"{label}: invalid baseline commit")
    if not isinstance(tree, str) or len(tree) != 40:
        raise SystemExit(f"{label}: invalid baseline tree")
    observed = subprocess.check_output(
        ["git", "rev-parse", f"{commit}^{{tree}}"], cwd=ROOT, text=True
    ).strip()
    if observed != tree:
        raise SystemExit(f"{label}: baseline tree mismatch")
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, "HEAD"], cwd=ROOT, check=True
    )


def verify_receipt_boundary(version: str, expected: list[str]) -> None:
    path = ROOT / "planning/evidence/repository" / (
        f"HEPTABAO_V{version}_POST_MERGE_CLOSURE_RECEIPT.yaml"
    )
    if not path.is_file():
        raise SystemExit(f"missing stage receipt: {path.relative_to(ROOT)}")
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected mapping")
    if value.get("claims") != CLAIMS:
        raise SystemExit(f"{path.name}: authority boundary drift")
    if value.get("external_or_control_blockers_closed") != []:
        raise SystemExit(f"{path.name}: external/control blocker overclaim")
    closed = value.get("closed_repository_blockers")
    if value.get("not_a_closure_receipt") is True:
        if closed != []:
            raise SystemExit(f"{path.name}: stage record closes repository blockers")
    elif closed != expected:
        raise SystemExit(f"{path.name}: repository blocker set mismatch")


def main() -> int:
    names = workspace_names()
    required = REQUIRED_V150 | REQUIRED_V160 | REQUIRED_V170 | REQUIRED_V180
    if len(names) != 42:
        raise SystemExit(f"expected 42 cumulative crates, observed {len(names)}")
    if not required.issubset(names):
        raise SystemExit(f"successor workspace lost crates: {sorted(required - names)}")

    previous_names: set[str] = set()
    for stage in STAGES:
        status = load(stage["status"])
        blockers = load(stage["blockers"])
        truth = load(stage["truth"])
        for label, value in (("status", status), ("blockers", blockers), ("truth", truth)):
            if value.get("claims") != CLAIMS:
                raise SystemExit(f"{stage['name']} {label}: authority boundary drift")
        verify_source_baseline(f"{stage['name']} status", status)
        if blockers.get("source_baseline") != status.get("source_baseline"):
            raise SystemExit(f"{stage['name']}: status/blocker baseline mismatch")
        added = blockers.get("added_blockers") or []
        if [item.get("id") for item in added] != stage["ids"]:
            raise SystemExit(f"{stage['name']}: blocker set mismatch")
        if any(item.get("state") != "IMPLEMENTED_SOURCE_REVIEW_REQUIRED" for item in added):
            raise SystemExit(f"{stage['name']}: repository blocker was prematurely closed")
        modules = truth.get("modules") or []
        stage_names = {item.get("crate") for item in modules}
        if truth.get("module_count") != stage["module_count"] or len(modules) != stage["module_count"]:
            raise SystemExit(f"{stage['name']}: module count mismatch")
        if len(stage_names) != stage["module_count"] or None in stage_names:
            raise SystemExit(f"{stage['name']}: duplicate or invalid module truth")
        if not previous_names.issubset(stage_names):
            raise SystemExit(f"{stage['name']}: historical module disappeared")
        if not stage_names.issubset(names):
            raise SystemExit(f"{stage['name']}: historical module missing from current workspace")
        previous_names = stage_names
        if not (ROOT / stage["plan"]).is_file():
            raise SystemExit(f"{stage['name']}: plan document missing")

    current_truth = load("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml")
    current_names = {item.get("crate") for item in current_truth.get("modules") or []}
    if current_names != names or current_truth.get("module_count") != 42:
        raise SystemExit("current V1.8 module truth/workspace mismatch")
    for item in current_truth.get("modules") or []:
        guide = ROOT / str(item.get("module_guide"))
        if not guide.is_file():
            raise SystemExit(f"missing current module guide: {guide.relative_to(ROOT)}")

    current = (ROOT / "docs/CURRENT_DOCUMENTATION.md").read_text(encoding="utf-8")
    if "HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md" not in current:
        raise SystemExit("current documentation does not select the V1.8 cumulative source")

    verify_receipt_boundary("1_4_7", STAGES[0]["ids"])
    verify_receipt_boundary("1_5_0", STAGES[1]["ids"])
    verify_receipt_boundary("1_6_0", STAGES[2]["ids"])
    verify_receipt_boundary("1_7_0", STAGES[3]["ids"])

    protocol = (ROOT / "crates/heptabao-protocol/src/lib.rs").read_text(encoding="utf-8")
    durable = (ROOT / "crates/heptabao-durable-core/src/lib.rs").read_text(encoding="utf-8")
    journaled = (ROOT / "crates/heptabao-journaled-core/src/lib.rs").read_text(encoding="utf-8")
    recovery = (ROOT / "crates/heptabao-recovery-core/src/lib.rs").read_text(encoding="utf-8")
    filesystem = (ROOT / "crates/heptabao-filesystem-guard/src/lib.rs").read_text(encoding="utf-8")
    for label, text, tokens in (
        ("protocol", protocol, ("parse_http_request", "RequestEnvelope", "SecretBytes")),
        ("durable", durable, ("prepare_persist", "commit_prepared", "recover_commit")),
        ("journaled", journaled, ("IntentCommitted", "recover_durable_intent", "StateCommitted")),
        ("recovery", recovery, ("stage_if_empty", "AnchorFenceOutcomeUnknown", "RecoveryRestorer")),
        ("filesystem", filesystem, ("O_NOFOLLOW", "ExclusiveDirectory", "WriterBusy")),
    ):
        for token in tokens:
            if token not in text:
                raise SystemExit(f"inherited {label} invariant token missing: {token}")

    print(
        "PASS cumulative inherited V1.4.7-V1.8 lineage: "
        "42 crates, blockers 059..093 review-required, external authority unchanged"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
