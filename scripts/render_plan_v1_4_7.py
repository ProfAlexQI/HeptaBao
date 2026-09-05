#!/usr/bin/env python3
"""Render V1.4.7 using the frozen generator with corrected shell escaping.

The original generator is kept byte-for-byte for a reviewable, narrow repair.
No workflow, test, authority claim or generated input is read back as its own
expected value. Check mode remains read-only and compares complete output bytes.
"""
from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
from typing import Any

BASELINE_PATH = Path(__file__).with_name("_render_plan_v1_4_7_baseline.py")
BASELINE_SHA256 = "ed72827409aac7da450dce4100365c49bb8ea3a2210fe0767030e2c5c9824aed"
if hashlib.sha256(BASELINE_PATH.read_bytes()).hexdigest() != BASELINE_SHA256:
    raise ValueError("frozen V1.4.7 generator integrity mismatch")
SPEC = importlib.util.spec_from_file_location("heptabao_v147_frozen_renderer", BASELINE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load frozen V1.4.7 generator")
BASELINE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASELINE)
_ORIGINAL_WORKFLOW = BASELINE.workflow_source
_ORIGINAL_PATHS = BASELINE.normative_paths


def workflow_source() -> str:
    source = _ORIGINAL_WORKFLOW()
    replacements = (
        ("printf 'source_kind=%s\nsource_sha=%s\ntree=%s\n'",
         r"printf 'source_kind=%s\nsource_sha=%s\ntree=%s\n'"),
        ('compatibility_claim: true"             planning/',
         'compatibility_claim: true" ' + "\\" + "\n" + "            planning/"),
    )
    for before, after in replacements:
        if source.count(before) != 1:
            raise ValueError("frozen workflow escape anchor mismatch")
        source = source.replace(before, after, 1)
    return source


def normative_paths(truth: dict[str, Any]) -> list[Path]:
    additions = {
        Path("scripts/_render_plan_v1_4_7_baseline.py"),
        Path("tests/plan/test_workflow_render_v1_4_7.py"),
    }
    return sorted(set(_ORIGINAL_PATHS(truth)) | additions, key=lambda path: path.as_posix())


BASELINE.workflow_source = workflow_source
BASELINE.normative_paths = normative_paths


def __getattr__(name: str) -> Any:
    # Preserve the generator's public inspection API used by existing tests.
    return getattr(BASELINE, name)


if __name__ == "__main__":
    raise SystemExit(BASELINE.main())
