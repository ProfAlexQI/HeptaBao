#!/usr/bin/env python3
"""Validate the V1.7 source stage without pretending it was merged.

This gate is used only by the V1.9 convergence controller between materializing
V1.7 and V1.8.  It verifies the 37-crate source/document surface, review-required
blocker states, and the explicit non-closure predecessor record.  The ordinary
standalone V1.7 validator remains unchanged and continues to require a real
reviewed two-parent merge.
"""
from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path

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
EXPECTED_NEW = {
    "heptabao-http-api",
    "heptabao-ha-core",
    "heptabao-plugin-host",
    "heptabao-compat-runner",
    "heptabao-client-tools",
}
RECEIPT_PATH = Path(
    "planning/evidence/repository/HEPTABAO_V1_6_0_POST_MERGE_CLOSURE_RECEIPT.yaml"
)


def load(path: Path) -> dict:
    value = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected mapping")
    return value


def workspace_names() -> set[str]:
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in cargo["workspace"]["members"]:
        for path in ROOT.glob(entry):
            manifest = path / "Cargo.toml"
            if not manifest.is_file():
                continue
            name = tomllib.loads(manifest.read_text(encoding="utf-8"))["package"]["name"]
            if name in names:
                raise SystemExit(f"duplicate workspace package {name}")
            names.add(name)
    return names


def main() -> int:
    status = load(Path("planning/HEPTABAO_V1_7_0_SERVICE_HA_STATUS.yaml"))
    blockers = load(Path("planning/HEPTABAO_BLOCKER_REGISTER_V1_7_0.yaml"))
    receipt = load(RECEIPT_PATH)
    truth = load(Path("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_7_0.yaml"))

    for label, value in (("status", status), ("blockers", blockers), ("receipt", receipt), ("truth", truth)):
        if value.get("claims") != CLAIMS:
            raise SystemExit(f"{label}: authority boundary drift")

    if receipt.get("schema") != "heptabao.unmerged-source-stage-record.v1":
        raise SystemExit("V1.6 predecessor object is not an unmerged-stage record")
    if receipt.get("status") != "SUPERSEDED_UNMERGED_SOURCE_STAGE":
        raise SystemExit("V1.6 predecessor stage status drift")
    if receipt.get("not_a_closure_receipt") is not True:
        raise SystemExit("V1.6 predecessor stage could be misread as closure")
    if receipt.get("original_path") != RECEIPT_PATH.as_posix():
        raise SystemExit("V1.6 predecessor stage path mismatch")
    if receipt.get("closed_repository_blockers") != []:
        raise SystemExit("unmerged V1.6 stage closes repository blockers")
    if receipt.get("external_or_control_blockers_closed") != []:
        raise SystemExit("unmerged V1.6 stage closes external/control blockers")

    added = blockers.get("added_blockers") or []
    expected_ids = [f"HB-BLK-REPO-{number:03d}" for number in range(79, 86)]
    if [item.get("id") for item in added] != expected_ids:
        raise SystemExit("V1.7 blocker set mismatch")
    if any(item.get("state") != "IMPLEMENTED_SOURCE_REVIEW_REQUIRED" for item in added):
        raise SystemExit("V1.7 repository blocker was prematurely closed")

    names = workspace_names()
    if len(names) != 37:
        raise SystemExit(f"V1.7 convergence expected 37 crates, observed {len(names)}")
    if not EXPECTED_NEW.issubset(names):
        raise SystemExit(f"V1.7 convergence missing crates {sorted(EXPECTED_NEW - names)}")
    truth_names = {item.get("crate") for item in truth.get("modules") or []}
    if truth.get("module_count") != 37 or truth_names != names:
        raise SystemExit("V1.7 module truth/workspace mismatch")
    for item in truth.get("modules") or []:
        guide = ROOT / str(item.get("module_guide"))
        if not guide.is_file():
            raise SystemExit(f"missing V1.7 module guide {guide}")

    workflow = ROOT / ".github/workflows/plan-v1.7.0-service-ha-plugin-compatibility.yml"
    if not workflow.is_file():
        raise SystemExit("V1.7 candidate workflow missing")
    generated_validator = ROOT / "scripts/validate_plan_v1_7_0.py"
    compile(generated_validator.read_text(encoding="utf-8"), str(generated_validator), "exec")
    subprocess.run(
        ["python", "scripts/render_module_source_truth_v1_7_0.py", "--check"],
        cwd=ROOT,
        check=True,
    )
    print("PASS V1.7 unmerged convergence source stage: 37 crates, no closure claim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
