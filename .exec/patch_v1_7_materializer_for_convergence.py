#!/usr/bin/env python3
"""Adapt the pinned V1.7 materializer for truthful V1.9 convergence.

V1.7's standalone materializer requires a real two-parent predecessor merge and
writes a post-merge closure receipt.  V1.9 deliberately converges the unmerged
V1.5-V1.8 source stages onto one reviewed candidate, so manufacturing that merge
would be false.  This helper changes only the execution copy: a single-parent
source is accepted exclusively when the convergence environment flag is set,
and the predecessor object becomes an explicit non-closure stage record.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

PARENT_OLD = '''    parent_line = run(root, "git", "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parent_line) != 3:
        raise SystemExit("V1.7 predecessor must be a two-parent integration merge")
    base_parent, reviewed_head = parent_line[1], parent_line[2]
'''
PARENT_NEW = '''    parent_line = run(root, "git", "rev-list", "--parents", "-n", "1", "HEAD").split()
    convergence = __import__("os").environ.get("HEPTABAO_V190_UNMERGED_CONVERGENCE") == "1"
    if len(parent_line) == 3:
        base_parent, reviewed_head = parent_line[1], parent_line[2]
    elif convergence and len(parent_line) == 2:
        base_parent, reviewed_head = parent_line[1], baseline
    else:
        raise SystemExit("V1.7 predecessor requires a two-parent integration merge outside V1.9 convergence")
'''
RECEIPT_OLD = '''def predecessor_receipt(
    baseline: str,
    tree: str,
    base_parent: str,
    reviewed_head: str,
) -> dict[str, Any]:
    return {
'''
RECEIPT_NEW = '''def predecessor_receipt(
    baseline: str,
    tree: str,
    base_parent: str,
    reviewed_head: str,
) -> dict[str, Any]:
    if __import__("os").environ.get("HEPTABAO_V190_UNMERGED_CONVERGENCE") == "1":
        path = "planning/evidence/repository/HEPTABAO_V1_6_0_POST_MERGE_CLOSURE_RECEIPT.yaml"
        return {
            "schema": "heptabao.unmerged-source-stage-record.v1",
            "plan_id": PLAN_ID,
            "status": "SUPERSEDED_UNMERGED_SOURCE_STAGE",
            "not_a_closure_receipt": True,
            "original_path": path,
            "reason": (
                "V1.6.0 source is being materialized into the V1.9.0 convergence candidate. "
                "No predecessor merge, approval, bypass waiver, qualification, or authority is claimed."
            ),
            "source_commit": baseline,
            "source_tree": tree,
            "closed_repository_blockers": [],
            "external_or_control_blockers_closed": [],
            "claims": CLAIMS,
        }
    return {
'''


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    raw = args.path.read_bytes()
    text = raw.decode("utf-8")
    if text.count(PARENT_OLD) != 1:
        raise SystemExit(f"V1.7 parent-contract count is {text.count(PARENT_OLD)}, expected 1")
    if text.count(RECEIPT_OLD) != 1:
        raise SystemExit(f"V1.7 predecessor-receipt count is {text.count(RECEIPT_OLD)}, expected 1")
    if "HEPTABAO_V190_UNMERGED_CONVERGENCE" in text:
        raise SystemExit("V1.7 materializer unexpectedly already contains convergence handling")

    patched = text.replace(PARENT_OLD, PARENT_NEW).replace(RECEIPT_OLD, RECEIPT_NEW)
    compile(patched, str(args.path), "exec")
    args.path.write_text(patched, encoding="utf-8")
    print(
        "PASS adapted V1.7 materializer for unmerged convergence "
        f"source_sha256={sha256(raw)} patched_sha256={sha256(patched.encode('utf-8'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
