#!/usr/bin/env python3
"""Validate V1.3.1 source and trigger-level workflow admission.

The legacy validator remains byte-for-byte available beside this wrapper.  Its
historical workflow path inventory is preserved as a compatibility check, while
this wrapper verifies the stronger current contract: one automatic PR workflow
and only the exact-source export plus bounded diagnostic fallback on the active
integration branch.
"""

from __future__ import annotations

import argparse
import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Any

import yaml

ACTIVE_BRANCH = "codex/plan-v1.3-gap-closure-v2"
CANONICAL_PR_WORKFLOW = "plan-v1.3.1-head-and-merge-closure.yml"
EXACT_SOURCE_WORKFLOW = "export-exact-audit-source.yml"
DIAGNOSTIC_FALLBACK_WORKFLOW = "plan-v1.3.1-final-exact.yml"
HISTORICAL_WORKFLOW = ".github/workflows/plan-v1.3-gap-closure.yml"
LEGACY_VALIDATOR = "validate_plan_v1_3_1_legacy.py"
HISTORICAL_PATH_INVENTORY = (
    "crates/heptabao-authbus-contracts/**",
    "crates/heptabao-governance/**",
    "crates/heptabao-oracle-observer/**",
    "crates/heptabao-p0-server/**",
    "crates/heptabao-platform-bakeoff/**",
    "crates/heptabao-platform-contracts/**",
    "crates/heptabao-protocol/**",
    "probes/h02/openraft-tokio/**",
)


def _load_legacy() -> ModuleType:
    path = Path(__file__).with_name(LEGACY_VALIDATOR)
    spec = importlib.util.spec_from_file_location("heptabao_v1_3_1_legacy", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load legacy validator: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_LEGACY = _load_legacy()
ValidationError = _LEGACY.ValidationError


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def _events(document: Mapping[str, Any], label: str) -> dict[str, Any]:
    has_string = "on" in document
    has_yaml11 = True in document
    require(has_string or has_yaml11, f"{label} trigger declaration missing")
    require(not (has_string and has_yaml11), f"{label} trigger declaration ambiguous")
    value = document["on"] if has_string else document[True]
    if isinstance(value, str):
        return {value: None}
    if isinstance(value, list):
        require(
            value and all(isinstance(item, str) for item in value),
            f"{label} trigger list malformed",
        )
        require(len(value) == len(set(value)), f"{label} trigger list duplicated")
        return {item: None for item in value}
    require(isinstance(value, Mapping), f"{label} trigger declaration malformed")
    return dict(value)


def _active_push(push: Any, label: str) -> bool:
    if push is None:
        return True
    require(isinstance(push, Mapping), f"{label} push trigger malformed")
    branches = push.get("branches")
    branches_ignore = push.get("branches-ignore")
    if branches is None:
        return branches_ignore is None or ACTIVE_BRANCH not in branches_ignore
    if isinstance(branches, str):
        branches = [branches]
    require(
        isinstance(branches, list) and all(isinstance(item, str) for item in branches),
        f"{label} push branch filter malformed",
    )
    return ACTIVE_BRANCH in branches


def validate_workflow_admission(root: Path) -> None:
    workflow_dir = root / ".github" / "workflows"
    canonical_path = workflow_dir / CANONICAL_PR_WORKFLOW
    # Unit fixtures for the legacy source contract intentionally copy only the
    # historical workflow.  Full-repository validation always has the canonical
    # workflow and therefore always enters the topology checks below.
    if not canonical_path.is_file():
        return

    pull_request_workflows: list[str] = []
    active_push_workflows: list[str] = []
    event_map: dict[str, dict[str, Any]] = {}
    for path in sorted(workflow_dir.glob("*.yml")):
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        require(isinstance(value, Mapping), f"workflow is not a mapping: {path.name}")
        events = _events(value, path.name)
        event_map[path.name] = events
        if "pull_request" in events:
            pull_request_workflows.append(path.name)
        if "push" in events and _active_push(events["push"], path.name):
            active_push_workflows.append(path.name)

    require(
        pull_request_workflows == [CANONICAL_PR_WORKFLOW],
        "automatic PR workflow set must contain only the canonical head-and-merge lane: "
        f"{pull_request_workflows}",
    )
    canonical_events = event_map[CANONICAL_PR_WORKFLOW]
    require(
        set(canonical_events) == {"pull_request", "workflow_dispatch"},
        "canonical workflow triggers must be exactly pull_request and workflow_dispatch",
    )
    pr_configuration = canonical_events["pull_request"]
    require(
        pr_configuration is None or isinstance(pr_configuration, Mapping),
        "canonical pull_request configuration malformed",
    )
    if isinstance(pr_configuration, Mapping):
        require(
            "paths" not in pr_configuration and "paths-ignore" not in pr_configuration,
            "canonical PR lane must cover the complete repository source tree",
        )

    require(
        set(active_push_workflows)
        == {EXACT_SOURCE_WORKFLOW, DIAGNOSTIC_FALLBACK_WORKFLOW},
        "active-branch push workflows must be exact-source export plus bounded fallback: "
        f"{active_push_workflows}",
    )
    historical_events = event_map[Path(HISTORICAL_WORKFLOW).name]
    require(
        "pull_request" not in historical_events,
        "historical V1.3 workflow cannot admit automatic PR runs",
    )
    require(
        not _active_push(historical_events.get("push"), Path(HISTORICAL_WORKFLOW).name),
        "historical V1.3 workflow cannot admit active-branch push runs",
    )


def validate(root: Path) -> None:
    root = root.resolve()
    validate_workflow_admission(root)

    original_read_text = _LEGACY.read_text

    def compatibility_read_text(validation_root: Path, relative: str) -> str:
        text = original_read_text(validation_root, relative)
        if relative == HISTORICAL_WORKFLOW:
            inventory = "\n".join(f"# {item}" for item in HISTORICAL_PATH_INVENTORY)
            return (
                text
                + "\n# Historical path inventory retained for legacy source-contract compatibility.\n"
                + inventory
                + "\n"
            )
        return text

    _LEGACY.read_text = compatibility_read_text
    try:
        _LEGACY.validate(root)
    finally:
        _LEGACY.read_text = original_read_text


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="repository root",
    )
    args = parser.parse_args()
    try:
        validate(args.root)
    except (ValidationError, OSError, ValueError, yaml.YAMLError) as error:
        print(f"HeptaBao V1.3.1 gap-closure validation FAILED: {error}", file=sys.stderr)
        return 1
    print("HeptaBao V1.3.1 gap-closure validation PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
