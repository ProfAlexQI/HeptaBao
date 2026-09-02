#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any


def api(repo: str, endpoint: str) -> Any:
    return json.loads(
        subprocess.check_output(
            ["gh", "api", f"repos/{repo}/{endpoint}"],
            text=True,
        )
    )


def text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value == "null":
        raise SystemExit(f"missing {label}")
    return value


def discover(repo: str, head_branch: str, base_branch: str) -> int:
    found: list[int] = []
    for page in range(1, 101):
        query = urllib.parse.urlencode(
            {"state": "closed", "per_page": 100, "page": page, "sort": "updated"}
        )
        pulls = api(repo, f"pulls?{query}")
        if not isinstance(pulls, list):
            raise SystemExit("pull discovery response is not an array")
        for pull in pulls:
            head = pull.get("head") or {}
            base = pull.get("base") or {}
            if (
                pull.get("merged_at")
                and head.get("ref") == head_branch
                and base.get("ref") == base_branch
                and ((head.get("repo") or {}).get("full_name")) == repo
                and isinstance(pull.get("number"), int)
            ):
                found.append(pull["number"])
        if len(pulls) < 100:
            break
    unique = sorted(set(found))
    if len(unique) != 1:
        raise SystemExit(
            f"expected one merged PR for {head_branch}->{base_branch}; observed={unique}"
        )
    return unique[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--expected-head-branch", required=True)
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--required-reviewer", action="append", default=[])
    parser.add_argument("--required-workflow", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")

    number = discover(
        args.repository,
        args.expected_head_branch,
        args.integration_branch,
    )
    pull = api(args.repository, f"pulls/{number}")
    if pull.get("state") != "closed" or pull.get("merged") is not True:
        raise SystemExit(f"PR #{number} is not merged")
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    if head.get("ref") != args.expected_head_branch:
        raise SystemExit("head branch mismatch")
    if base.get("ref") != args.integration_branch:
        raise SystemExit("base branch mismatch")
    if ((head.get("repo") or {}).get("full_name")) != args.repository:
        raise SystemExit("head repository mismatch")

    reviewed_head = text(head.get("sha"), "reviewed head")
    merge_commit = text(pull.get("merge_commit_sha"), "merge commit")
    base_commit = text(base.get("sha"), "base commit")
    author = text((pull.get("user") or {}).get("login"), "PR author")

    reviews = api(args.repository, f"pulls/{number}/reviews?per_page=100")
    if not isinstance(reviews, list):
        raise SystemExit("review response is not an array")
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=lambda item: item.get("submitted_at") or ""):
        login = (review.get("user") or {}).get("login")
        if isinstance(login, str) and login:
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
        raise SystemExit("missing eligible exact-head approvals: " + ", ".join(waiting))
    blocking = sorted(
        login
        for login, review in latest.items()
        if review.get("commit_id") == reviewed_head
        and review.get("state") == "CHANGES_REQUESTED"
    )
    if blocking:
        raise SystemExit("current-head changes requested by: " + ", ".join(blocking))

    query = urllib.parse.urlencode(
        {"event": "pull_request", "head_sha": reviewed_head, "per_page": 100}
    )
    payload = api(args.repository, f"actions/runs?{query}")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise SystemExit("workflow response is not an array")
    latest_runs: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: item.get("id") or 0):
        name = run.get("name")
        if isinstance(name, str):
            latest_runs[name] = run
    missing = sorted(set(args.required_workflow) - set(latest_runs))
    if missing:
        raise SystemExit("missing workflow families: " + ", ".join(missing))
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
        raise SystemExit("workflow admission failed: " + "; ".join(bad))

    encoded = urllib.parse.quote(args.integration_branch, safe="")
    integration = api(args.repository, f"branches/{encoded}")
    integration_head = text(
        ((integration.get("commit") or {}).get("sha")),
        "integration head",
    )
    if integration_head != merge_commit:
        raise SystemExit(
            f"integration head {integration_head} != merge commit {merge_commit}"
        )

    commit = api(args.repository, f"commits/{merge_commit}")
    if (((commit.get("commit") or {}).get("verification") or {}).get("verified")) is not True:
        raise SystemExit("merge commit is not GitHub verified")
    parents = [text(item.get("sha"), "merge parent") for item in commit.get("parents") or []]
    if parents != [base_commit, reviewed_head]:
        raise SystemExit(
            f"ordered merge parents mismatch: observed={parents} expected={[base_commit, reviewed_head]}"
        )
    merge_tree = text(
        ((((commit.get("commit") or {}).get("tree") or {}).get("sha"))),
        "merge tree",
    )

    result = {
        "repository": args.repository,
        "pull_request": number,
        "base_branch": args.integration_branch,
        "base_commit": base_commit,
        "reviewed_head": reviewed_head,
        "merge_commit": merge_commit,
        "merge_tree": merge_tree,
        "ordered_merge_parents": parents,
        "administrator_bypass": False,
        "authority_effect": "NONE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
