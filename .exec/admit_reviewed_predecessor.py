#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any


def gh(repository: str, endpoint: str) -> Any:
    output = subprocess.check_output(
        ["gh", "api", f"repos/{repository}/{endpoint}"],
        text=True,
    )
    return json.loads(output)


def require_text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value or value == "null":
        raise SystemExit(f"missing {name}")
    return value


def discover_pull_request(
    repository: str,
    expected_head_branch: str,
    integration_branch: str,
) -> int:
    matches: list[int] = []
    page = 1
    while True:
        query = urllib.parse.urlencode(
            {
                "state": "closed",
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            }
        )
        pulls = gh(repository, f"pulls?{query}")
        if not isinstance(pulls, list):
            raise SystemExit("pull-request discovery response is not an array")
        for pull in pulls:
            head = pull.get("head") or {}
            base = pull.get("base") or {}
            head_repo = head.get("repo") or {}
            if (
                pull.get("merged_at")
                and head.get("ref") == expected_head_branch
                and base.get("ref") == integration_branch
                and head_repo.get("full_name") == repository
            ):
                number = pull.get("number")
                if isinstance(number, int):
                    matches.append(number)
        if len(pulls) < 100:
            break
        page += 1
        if page > 100:
            raise SystemExit("pull-request discovery exceeded bounded pagination")
    unique = sorted(set(matches))
    if len(unique) != 1:
        raise SystemExit(
            "expected exactly one merged predecessor PR for "
            f"{expected_head_branch}->{integration_branch}, observed={unique}"
        )
    return unique[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int)
    parser.add_argument("--expected-head-branch", required=True)
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--required-reviewer", action="append", default=[])
    parser.add_argument("--required-workflow", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")

    pr_number = args.pr
    if pr_number is None:
        pr_number = discover_pull_request(
            args.repository,
            args.expected_head_branch,
            args.integration_branch,
        )

    pull = gh(args.repository, f"pulls/{pr_number}")
    if pull.get("state") != "closed" or pull.get("merged") is not True:
        raise SystemExit(f"PR #{pr_number} is not merged")
    if (pull.get("base") or {}).get("ref") != args.integration_branch:
        raise SystemExit("predecessor base branch mismatch")
    if (pull.get("head") or {}).get("ref") != args.expected_head_branch:
        raise SystemExit("predecessor head branch mismatch")
    if ((pull.get("head") or {}).get("repo") or {}).get("full_name") != args.repository:
        raise SystemExit("predecessor head repository mismatch")

    reviewed_head = require_text((pull.get("head") or {}).get("sha"), "reviewed head")
    merge_sha = require_text(pull.get("merge_commit_sha"), "merge commit")
    base_sha = require_text((pull.get("base") or {}).get("sha"), "base commit")
    author = require_text((pull.get("user") or {}).get("login"), "PR author")

    reviews = gh(args.repository, f"pulls/{pr_number}/reviews?per_page=100")
    if not isinstance(reviews, list):
        raise SystemExit("review response is not an array")
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=lambda item: item.get("submitted_at") or ""):
        login = (review.get("user") or {}).get("login")
        if login:
            latest[login] = review

    waiting = []
    for login in sorted(set(args.required_reviewer)):
        review = latest.get(login)
        if (
            not review
            or review.get("state") != "APPROVED"
            or review.get("commit_id") != reviewed_head
            or login == author
            or login.endswith("[bot]")
        ):
            waiting.append(login)
    if waiting:
        raise SystemExit(
            "predecessor lacks eligible exact-head approvals: " + ", ".join(waiting)
        )

    blocking = sorted(
        login
        for login, review in latest.items()
        if review.get("commit_id") == reviewed_head
        and review.get("state") == "CHANGES_REQUESTED"
    )
    if blocking:
        raise SystemExit(
            "predecessor has current-head change requests: " + ", ".join(blocking)
        )

    run_payload = gh(
        args.repository,
        "actions/runs?"
        + urllib.parse.urlencode(
            {
                "event": "pull_request",
                "head_sha": reviewed_head,
                "per_page": 100,
            }
        ),
    )
    runs = run_payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise SystemExit("workflow-run response is not an array")
    latest_runs: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: item.get("id") or 0):
        name = run.get("name")
        if isinstance(name, str):
            latest_runs[name] = run
    missing = sorted(set(args.required_workflow) - set(latest_runs))
    if missing:
        raise SystemExit("predecessor lacks workflow families: " + ", ".join(missing))
    bad = []
    for name in sorted(set(args.required_workflow)):
        run = latest_runs[name]
        if (
            run.get("head_sha") != reviewed_head
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            bad.append(
                f"{name}:{run.get('head_sha')}:{run.get('status')}:{run.get('conclusion')}"
            )
    if bad:
        raise SystemExit("predecessor workflow admission failed: " + "; ".join(bad))

    encoded_branch = urllib.parse.quote(args.integration_branch, safe="")
    branch = gh(args.repository, f"branches/{encoded_branch}")
    integration_sha = require_text(
        ((branch.get("commit") or {}).get("sha")),
        "integration head",
    )
    if integration_sha != merge_sha:
        raise SystemExit(
            f"integration head {integration_sha} does not equal merge {merge_sha}"
        )

    commit = gh(args.repository, f"commits/{merge_sha}")
    verification = ((commit.get("commit") or {}).get("verification") or {})
    if verification.get("verified") is not True:
        raise SystemExit("predecessor merge is not GitHub verified")
    parents = [
        require_text(parent.get("sha"), "merge parent")
        for parent in commit.get("parents") or []
    ]
    if parents != [base_sha, reviewed_head]:
        raise SystemExit(
            f"ordered merge parents mismatch: observed={parents} "
            f"expected={[base_sha, reviewed_head]}"
        )
    merge_tree = require_text(
        (((commit.get("commit") or {}).get("tree") or {}).get("sha")),
        "merge tree",
    )

    value = {
        "repository": args.repository,
        "pull_request": pr_number,
        "base_branch": args.integration_branch,
        "base_commit": base_sha,
        "reviewed_head": reviewed_head,
        "merge_commit": merge_sha,
        "merge_tree": merge_tree,
        "ordered_merge_parents": parents,
        "required_reviewers": sorted(set(args.required_reviewer)),
        "required_workflows": sorted(set(args.required_workflow)),
        "administrator_bypass": False,
        "authority_effect": "NONE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(value, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
