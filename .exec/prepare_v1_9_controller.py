#!/usr/bin/env python3
"""Create an execution copy of the V1.9 controller with bound repairs.

The committed controller remains the immutable forensic input. This helper
applies only exact-count substitutions to its execution copy:

* permit an explicitly supplied staging branch while retaining the canonical default;
* make the V1.7 materializer filename match the V3 asset patch contract;
* adapt V1.7 to the truthful V1.9 unmerged-stage model and validate that stage;
* narrow the pinned V1.8 patch script to the unique service test module;
* repair the pinned V1.8 materializer's nested renderer string delimiters;
* regenerate Cargo.lock after all 42 workspace members have been materialized;
* patch the two source-bound defects in the generated V1.9 workflow.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

CANONICAL_CANDIDATE = "codex/plan-v1.9.0-full-repository-convergence-v1"
CANDIDATE_LINE = f'CANDIDATE_BRANCH="{CANONICAL_CANDIDATE}"'
CANDIDATE_REPLACEMENT = (
    f'CANDIDATE_BRANCH="${{HEPTABAO_CANDIDATE_BRANCH:-{CANONICAL_CANDIDATE}}}"'
)
WORK_SETUP = 'mkdir -p "$WORK/v150" "$WORK/v160" "$WORK/v170/archive" "$WORK/v180" "$WORKFLOWS"'
WORK_SETUP_REPLACEMENT = (
    WORK_SETUP
    + '\ncp .exec/validate_v1_7_stage_for_convergence.py '
    + '"$WORK/validate_v1_7_stage_for_convergence.py"'
)
GENERATOR_CHECK = 'python -m py_compile "$WORK/converge_v1_9.py" "$WORK/augment_external_v2.py"'
GENERATOR_INSERT = (
    'python .exec/patch_v1_9_generator.py "$WORK/converge_v1_9.py"\n'
    + GENERATOR_CHECK
)
V170_OLD = '$WORK/v170/materialize.py'
V170_NEW = '$WORK/v170/materialize_v1_7_0.py'
V170_REFERENCE_COUNT = 3
V170_LAST_ASSET_PATCH = 'python "$WORK/v170/archive/.exec/patch_v1_7_assets_v3.py" "$WORK/v170/assets"'
V170_LAST_ASSET_PATCH_REPLACEMENT = (
    V170_LAST_ASSET_PATCH
    + '\npython .exec/patch_v1_7_materializer_for_convergence.py '
    + '"$WORK/v170/materialize_v1_7_0.py"'
)
V170_MATERIALIZE_COMMAND = (
    'python "$WORK/v170/materialize_v1_7_0.py" . --asset-root "$WORK/v170/assets"'
)
V170_MATERIALIZE_REPLACEMENT = (
    'HEPTABAO_V190_UNMERGED_CONVERGENCE=1 ' + V170_MATERIALIZE_COMMAND
)
V170_VALIDATION_BLOCK = (
    'python scripts/render_module_source_truth_v1_7_0.py --check\n'
    'python scripts/validate_plan_v1_7_0.py'
)
V170_VALIDATION_REPLACEMENT = (
    'python scripts/render_module_source_truth_v1_7_0.py --check\n'
    'python "$WORK/validate_v1_7_stage_for_convergence.py"'
)
V180_PATCH_COMMAND = 'python "$WORK/v180/patch.py" "$WORK/v180/materialize.py"'
V180_PATCH_INSERT = (
    'python .exec/patch_v1_8_patch_script.py "$WORK/v180/patch.py"\n'
    + V180_PATCH_COMMAND
    + '\npython .exec/patch_v1_8_materializer.py "$WORK/v180/materialize.py"'
)
V180_MATERIALIZE_COMMAND = 'python "$WORK/v180/materialize.py" .'
V180_MATERIALIZE_INSERT = (
    V180_MATERIALIZE_COMMAND
    + '\n# All V1.5-V1.8 workspace members now exist; freeze the exact path-only graph '
    + 'before any --locked gate.\n'
    + 'cargo +1.98.0 generate-lockfile --manifest-path Cargo.toml'
)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def require_count(source: str, needle: str, expected: int, label: str) -> None:
    actual = source.count(needle)
    if actual != expected:
        raise SystemExit(f"{label} count is {actual}, expected {expected}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    require_count(source, CANDIDATE_LINE, 1, "canonical candidate assignment")
    require_count(source, WORK_SETUP, 1, "controller work setup")
    require_count(source, GENERATOR_CHECK, 1, "controller generator insertion point")
    require_count(source, V170_OLD, V170_REFERENCE_COUNT, "V1.7 materializer reference")
    require_count(source, V170_LAST_ASSET_PATCH, 1, "V1.7 asset-patch insertion point")
    require_count(source, V180_PATCH_COMMAND, 1, "V1.8 patch invocation")
    require_count(source, V180_MATERIALIZE_COMMAND, 1, "V1.8 materializer invocation")
    for unexpected in (
        "patch_v1_9_generator.py",
        "patch_v1_7_materializer_for_convergence.py",
        "validate_v1_7_stage_for_convergence.py",
        "patch_v1_8_patch_script.py",
        "patch_v1_8_materializer.py",
        "cargo +1.98.0 generate-lockfile",
        "HEPTABAO_CANDIDATE_BRANCH",
        "HEPTABAO_V190_UNMERGED_CONVERGENCE",
    ):
        if unexpected in source:
            raise SystemExit(f"committed controller already contains unexpected repair {unexpected!r}")
    if V170_NEW in source:
        raise SystemExit("committed controller unexpectedly already uses the repaired V1.7 path")

    prepared = source.replace(CANDIDATE_LINE, CANDIDATE_REPLACEMENT)
    prepared = prepared.replace(WORK_SETUP, WORK_SETUP_REPLACEMENT)
    prepared = prepared.replace(V170_OLD, V170_NEW)
    prepared = prepared.replace(V170_LAST_ASSET_PATCH, V170_LAST_ASSET_PATCH_REPLACEMENT)
    require_count(prepared, V170_MATERIALIZE_COMMAND, 1, "prepared V1.7 materializer invocation")
    require_count(prepared, V170_VALIDATION_BLOCK, 1, "prepared V1.7 validation block")
    prepared = prepared.replace(V170_MATERIALIZE_COMMAND, V170_MATERIALIZE_REPLACEMENT)
    prepared = prepared.replace(V170_VALIDATION_BLOCK, V170_VALIDATION_REPLACEMENT)
    prepared = prepared.replace(V180_PATCH_COMMAND, V180_PATCH_INSERT)
    prepared = prepared.replace(V180_MATERIALIZE_COMMAND, V180_MATERIALIZE_INSERT)
    prepared = prepared.replace(GENERATOR_CHECK, GENERATOR_INSERT)

    require_count(prepared, "HEPTABAO_CANDIDATE_BRANCH", 1, "prepared candidate override")
    require_count(prepared, V170_NEW, V170_REFERENCE_COUNT, "prepared V1.7 path")
    require_count(prepared, "patch_v1_7_materializer_for_convergence.py", 1, "prepared V1.7 stage repair")
    require_count(prepared, "validate_v1_7_stage_for_convergence.py", 2, "prepared V1.7 stage validator")
    require_count(prepared, "HEPTABAO_V190_UNMERGED_CONVERGENCE", 1, "prepared V1.7 convergence flag")
    require_count(prepared, "patch_v1_8_patch_script.py", 1, "prepared V1.8 patch repair")
    require_count(prepared, "patch_v1_8_materializer.py", 1, "prepared V1.8 materializer repair")
    require_count(prepared, "cargo +1.98.0 generate-lockfile", 1, "prepared lockfile refresh")
    require_count(prepared, "patch_v1_9_generator.py", 1, "prepared V1.9 generator repair")
    if V170_OLD in prepared or CANDIDATE_LINE in prepared:
        raise SystemExit("controller preparation was incomplete")

    args.output.write_text(prepared, encoding="utf-8")
    args.output.chmod(0o700)
    print(
        "PASS prepared V1.9 controller "
        f"source_sha256={sha256(source)} "
        f"prepared_sha256={sha256(prepared)} "
        f"v170_path_repairs={V170_REFERENCE_COUNT} "
        "v170_unmerged_stage_repairs=1 v170_stage_validator=1 "
        "v180_patch_repairs=1 v180_materializer_repairs=1 "
        "lockfile_refresh=1 v190_generator_repairs=1"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
