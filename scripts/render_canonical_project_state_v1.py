#!/usr/bin/env python3
"""Resolve HeptaBao's static canonical-state input against an exact source tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

SHA40 = re.compile(r"^[0-9a-f]{40}$")


class Failure(RuntimeError):
    pass


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    try:
        return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()
    except (OSError, subprocess.CalledProcessError) as error:
        raise Failure(f"git {' '.join(args)} failed") from error


def resolve(args: argparse.Namespace) -> dict[str, Any]:
    root = Path(args.root).resolve()
    source_path = root / "planning/HEPTABAO_CANONICAL_PROJECT_STATE_V1.yaml"
    state = yaml.safe_load(source_path.read_text(encoding="utf-8"))
    if not isinstance(state, dict):
        raise Failure("canonical state input must be a mapping")
    if state.get("binding", {}).get("mode") != "SELF_RESOLVED_AT_VERIFICATION":
        raise Failure("canonical state input is not self-resolved")

    commit = args.commit or git(root, "rev-parse", "HEAD")
    tree = args.tree or git(root, "rev-parse", "HEAD^{tree}")
    ref = args.ref or git(root, "symbolic-ref", "--short", "-q", "HEAD") or "DETACHED"
    if not SHA40.fullmatch(commit) or not SHA40.fullmatch(tree):
        raise Failure("commit and tree must be full lowercase SHA-1 object IDs")
    if args.require_clean:
        status = git(root, "status", "--porcelain=v1", "--untracked-files=all")
        if status:
            raise Failure("source tree is not clean")

    manifest = yaml.safe_load(
        (root / "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1.yaml").read_text(encoding="utf-8")
    )
    documents = []
    for entry in manifest["documents"]:
        path = root / entry["path"]
        documents.append(
            {
                "id": entry["id"],
                "path": entry["path"],
                "kind": entry["kind"],
                "sha256": file_sha256(path),
            }
        )

    lock_path = root / "probes/h02/openraft-tokio/Cargo.lock"
    resolved: dict[str, Any] = {
        **state,
        "binding": {
            "mode": "EXACT_SOURCE_RESOLVED",
            "repository": args.repository,
            "ref": ref,
            "commit": commit,
            "tree": tree,
            "clean_tree": bool(args.require_clean),
        },
        "resolved_documents": documents,
        "resolved_artifacts": {
            "openraft_lock_path": str(lock_path.relative_to(root)),
            "openraft_lock_sha256": file_sha256(lock_path),
            "plan_validator_sha256": file_sha256(root / "scripts/validate_plan_v1_2.py"),
        },
        "execution_identity": {
            "environment_id": args.environment_id,
            "runner_id": args.runner_id,
            "runner_name": args.runner_name,
            "job_id": args.job_id,
            "run_id": args.run_id,
        },
        "qualification": False,
        "compatibility_claim": False,
        "authority_effect": "NONE",
    }
    return resolved


def parser() -> argparse.ArgumentParser:
    value = argparse.ArgumentParser()
    value.add_argument("--root", default=".")
    value.add_argument("--repository", default="ProfHepta/HeptaBao")
    value.add_argument("--ref")
    value.add_argument("--commit")
    value.add_argument("--tree")
    value.add_argument("--environment-id", default="unavailable")
    value.add_argument("--runner-id")
    value.add_argument("--runner-name")
    value.add_argument("--job-id")
    value.add_argument("--run-id")
    value.add_argument("--require-clean", action="store_true")
    value.add_argument("--output", required=True)
    return value


def main() -> int:
    args = parser().parse_args()
    try:
        result = resolve(args)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(result, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
    except (Failure, OSError, ValueError, KeyError, yaml.YAMLError) as error:
        print(f"canonical project-state resolution FAILED: {error}", file=sys.stderr)
        return 1
    print(
        "canonical project state resolved: "
        f"commit={result['binding']['commit']} tree={result['binding']['tree']} "
        "qualification=false authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
