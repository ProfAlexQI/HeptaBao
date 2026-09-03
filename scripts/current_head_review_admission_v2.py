#!/usr/bin/env python3
"""Live GitHub adapter for current-head repository-change admission V2."""
from __future__ import annotations

import argparse
import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

try:
    from scripts.review_admission_v2_core import (
        AdmissionError,
        REQUIRED_REVIEWERS,
        collect_pages,
        evaluate_snapshot,
        require,
    )
except ModuleNotFoundError:
    from review_admission_v2_core import (
        AdmissionError,
        REQUIRED_REVIEWERS,
        collect_pages,
        evaluate_snapshot,
        require,
    )

class GitHubApi:
    def __init__(self, repository: str, token: str) -> None:
        self.repository = repository
        self.token = token

    def get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        encoded_path = "/".join(urllib.parse.quote(part, safe="") for part in path.split("/"))
        url = f"https://api.github.com/repos/{self.repository}/{encoded_path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "heptabao-current-head-review-admission-v2",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise AdmissionError(f"GitHub API GET failed {error.code} {path}: {detail}") from error

    def pages(self, path: str, *, key: str | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        base = dict(params or {})
        return collect_pages(
            lambda page, per_page: self.get(path, {**base, "page": page, "per_page": per_page}),
            key=key,
        )


def build_live_snapshot(
    api: GitHubApi,
    pr_number: int,
    *,
    event_head_sha: str | None,
    event_base_sha: str | None,
) -> dict[str, Any]:
    pull = api.get(f"pulls/{pr_number}")
    head_sha = ((pull.get("head") or {}).get("sha"))
    prospective_sha = pull.get("merge_commit_sha")
    require(isinstance(head_sha, str) and head_sha, "live PR head missing")
    require(isinstance(prospective_sha, str) and prospective_sha, "live prospective merge missing")

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

    return {
        "repository": api.repository,
        "pull_request": pull,
        "event_head_sha": event_head_sha,
        "event_base_sha": event_base_sha,
        "head_commit": api.get(f"commits/{head_sha}"),
        "prospective_commit": api.get(f"commits/{prospective_sha}"),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int, required=True)
    parser.add_argument("--event-head-sha")
    parser.add_argument("--event-base-sha")
    parser.add_argument("--compute-marker", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if not args.repository or not token:
        raise SystemExit("repository and GH_TOKEN/GITHUB_TOKEN are required")

    try:
        api = GitHubApi(args.repository, token)
        snapshot = build_live_snapshot(
            api,
            args.pr,
            event_head_sha=args.event_head_sha,
            event_base_sha=args.event_base_sha,
        )
        result = evaluate_snapshot(snapshot, require_marker=not args.compute_marker)
    except AdmissionError as error:
        raise SystemExit(f"REVIEW_ADMISSION_DENIED: {error}") from error

    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
