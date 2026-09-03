#!/usr/bin/env python3
"""Recompute a V2 review packet after the reviewed pull request has merged."""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
from pathlib import Path
from typing import Any

try:
    from scripts.current_head_review_admission_v2 import GitHubApi
    from scripts.review_admission_v2_core import (
        AdmissionError,
        REQUIRED_REVIEWERS,
        commit_identity,
        evaluate_snapshot,
        require,
    )
except ModuleNotFoundError:
    from current_head_review_admission_v2 import GitHubApi
    from review_admission_v2_core import (
        AdmissionError,
        REQUIRED_REVIEWERS,
        commit_identity,
        evaluate_snapshot,
        require,
    )

PROSPECTIVE_RE = re.compile(
    r"(?m)^prospective merge:\s*([0-9a-f]{40})\s*$"
)


def prospective_from_body(body: str) -> str:
    matches = PROSPECTIVE_RE.findall(body)
    require(len(matches) == 1, f"expected exactly one frozen prospective merge in PR body, observed={matches}")
    return matches[0]


def synthetic_open_pull(pull: dict[str, Any], prospective_sha: str) -> dict[str, Any]:
    require(pull.get("state") == "closed", "archived pull request is not closed")
    require(pull.get("merged") is True, "archived pull request is not merged")
    require(pull.get("draft") is False, "archived pull request is draft")
    value = copy.deepcopy(pull)
    value["state"] = "open"
    value["draft"] = False
    value["mergeable"] = True
    value["merge_commit_sha"] = prospective_sha
    return value


def build_archived_snapshot(api: GitHubApi, pr_number: int) -> tuple[dict[str, Any], dict[str, Any]]:
    pull = api.get(f"pulls/{pr_number}")
    body = pull.get("body") or ""
    prospective_sha = prospective_from_body(body)
    final_merge_sha = pull.get("merge_commit_sha")
    head_sha = ((pull.get("head") or {}).get("sha"))
    base_sha = ((pull.get("base") or {}).get("sha"))
    for value, label in (
        (head_sha, "reviewed head"),
        (base_sha, "base commit"),
        (final_merge_sha, "final merge commit"),
    ):
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None, f"invalid {label}")

    head_commit_raw = api.get(f"commits/{head_sha}")
    prospective_raw = api.get(f"commits/{prospective_sha}")
    final_raw = api.get(f"commits/{final_merge_sha}")
    head = commit_identity(head_commit_raw, "reviewed head")
    prospective = commit_identity(prospective_raw, "frozen prospective merge")
    final = commit_identity(final_raw, "final merge")
    require(prospective["verified"], "frozen prospective merge is not GitHub verified")
    require(prospective["parents"] == [base_sha, head_sha], "frozen prospective merge parents are not ordered base/head")
    require(prospective["tree"] == head["tree"], "frozen prospective merge tree differs from reviewed head tree")
    require(final["verified"], "final merge is not GitHub verified")
    require(final["parents"] == [base_sha, head_sha], "final merge parents are not ordered base/head")
    require(final["tree"] == head["tree"], "final merge tree differs from reviewed head tree")

    codeowners = api.get("contents/.github/CODEOWNERS", {"ref": head_sha})
    encoded_content = codeowners.get("content")
    require(isinstance(encoded_content, str), "CODEOWNERS API content missing")
    try:
        codeowners_content = base64.b64decode(encoded_content).decode("utf-8")
    except (ValueError, UnicodeDecodeError) as error:
        raise AdmissionError("CODEOWNERS API content is invalid") from error

    permissions: dict[str, str] = {}
    for reviewer in REQUIRED_REVIEWERS:
        value = api.get(f"collaborators/{reviewer}/permission")
        permission = value.get("permission")
        require(isinstance(permission, str), f"{reviewer}: permission API result missing")
        permissions[reviewer] = permission

    snapshot = {
        "repository": api.repository,
        "pull_request": synthetic_open_pull(pull, prospective_sha),
        "event_head_sha": None,
        "event_base_sha": None,
        "head_commit": head_commit_raw,
        "prospective_commit": prospective_raw,
        "reviews": api.pages(f"pulls/{pr_number}/reviews"),
        "workflow_runs": api.pages(
            "actions/runs",
            key="workflow_runs",
            params={"event": "pull_request", "head_sha": head_sha},
        ),
        "permissions": permissions,
        "codeowners_sha": codeowners.get("sha"),
        "codeowners_content": codeowners_content,
    }
    final_packet = {
        "final_merge_sha": final_merge_sha,
        "final_merge_tree": final["tree"],
        "final_merge_parents": final["parents"],
        "final_merge_verified": True,
    }
    return snapshot, final_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not args.repository or not token:
        raise SystemExit("repository and GH_TOKEN/GITHUB_TOKEN are required")

    try:
        api = GitHubApi(args.repository, token)
        snapshot, final_packet = build_archived_snapshot(api, args.pr)
        result = evaluate_snapshot(snapshot)
        result["final_merge"] = final_packet
    except AdmissionError as error:
        raise SystemExit(f"ARCHIVED_REVIEW_ADMISSION_DENIED: {error}") from error

    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
