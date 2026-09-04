#!/usr/bin/env python3
"""Repair the two escaped-string defects in the frozen V1.4.7 renderer.

This is intentionally exact-count and source-bound. It does not weaken the
V1.4.7 validator: it repairs the generator, regenerates the normative manifest,
and then leaves the ordinary validator to check the complete source.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

RENDERER = Path("scripts/render_plan_v1_4_7.py")
MANIFEST = Path("planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml")
WORKFLOW = Path(".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml")

ORIGINAL_RENDERER_GIT_BLOB = "dc2eb7dac6ffc7b593c30876a381a1dbfeada51b"
REPAIRED_RENDERER_SHA256 = "19d0ba6c198dcd096c75fa47965167df70cc420c4eabab7bb27289478b907df2"
EXPECTED_WORKFLOW_SHA256 = "1cc4ea91a4d6760ae6c481b273a8a69c0cc8f8f0f53862fc4f445542eed612c6"

PRINTF_OLD = r"printf 'source_kind=%s\nsource_sha=%s\ntree=%s\n'"
PRINTF_NEW = r"printf 'source_kind=%s\\nsource_sha=%s\\ntree=%s\\n'"
GREP_OLD = (
    '"production_authority: true\\|release_authority: true\\|'
    'migration_authority: true\\|compatibility_claim: true" \\\n'
)
GREP_NEW = (
    '"production_authority: true\\\\|release_authority: true\\\\|'
    'migration_authority: true\\\\|compatibility_claim: true" \\\\\n'
)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} count is {count}, expected 1")
    return text.replace(old, new, 1)


def main() -> int:
    if not RENDERER.is_file() or not MANIFEST.is_file() or not WORKFLOW.is_file():
        raise SystemExit("V1.4.7 repair inputs are missing")

    current_blob = git_blob_sha(RENDERER)
    current_sha = sha256(RENDERER)
    if current_sha == REPAIRED_RENDERER_SHA256:
        print("V1.4.7 renderer is already repaired")
    else:
        if current_blob != ORIGINAL_RENDERER_GIT_BLOB:
            raise SystemExit(
                "refusing to patch an unknown V1.4.7 renderer: "
                f"git_blob={current_blob} sha256={current_sha}"
            )
        text = RENDERER.read_text(encoding="utf-8")
        text = replace_exact(text, PRINTF_OLD, PRINTF_NEW, "printf escape defect")
        text = replace_exact(text, GREP_OLD, GREP_NEW, "grep escape defect")
        RENDERER.write_text(text, encoding="utf-8")
        if sha256(RENDERER) != REPAIRED_RENDERER_SHA256:
            raise SystemExit("repaired renderer digest mismatch")

    subprocess.run(
        [sys.executable, str(RENDERER), "--write"],
        check=True,
    )

    workflow_digest = sha256(WORKFLOW)
    if workflow_digest != EXPECTED_WORKFLOW_SHA256:
        raise SystemExit(
            f"V1.4.7 workflow digest mismatch: {workflow_digest}"
        )
    manifest = MANIFEST.read_text(encoding="utf-8")
    if f"sha256: {EXPECTED_WORKFLOW_SHA256}" not in manifest:
        raise SystemExit("V1.4.7 manifest did not bind the repaired workflow")
    if f"sha256: {REPAIRED_RENDERER_SHA256}" not in manifest:
        raise SystemExit("V1.4.7 manifest did not bind the repaired renderer")

    print(
        "PASS repaired V1.4.7 renderer and regenerated manifest "
        f"renderer_sha256={REPAIRED_RENDERER_SHA256} "
        f"workflow_sha256={EXPECTED_WORKFLOW_SHA256}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
