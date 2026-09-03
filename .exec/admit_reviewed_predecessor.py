#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import urllib.parse
from pathlib import Path
from typing import Any

DECISIVE_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})


def command(*args: str) -> Any:
    return json.loads(subprocess.check_output(args, text=True))


def rest(repository: str, endpoint: str, **params: Any) -> Any:
    args = ["gh", "api", "--method", "GET", f"repos/{repository}/{endpoint}"]
    for name, value in params.items():
        args.extend(["-f", f"{name}={value}"])
    return command(*args)


def paged(
    repository: str,
    endpoint: str,
    *,
    key: str | None = None,
    **params: Any,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 101):
        payload = rest(
            repository,
            endpoint,
            **params,
            per_page=100,
            page=page,
        )
        values = payload.get(key) if key is not None and isinstance(payload, dict) else payload
        if not isinstance(values, list):
            raise SystemExit(f"paged response is not an array: {endpoint}")
        if any(not isinstance(item, dict) for item in values):
            raise SystemExit(f"paged response contains non-object item: {endpoint}")
        output.extend(values)
        if len(values) < 100:
            return output
    raise SystemExit(f"pagination exceeded bounded limit: {endpoint}")


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value == "null":
        raise SystemExit(f"missing {label}")
    return value


def discover(repository: str, head_branch: str, base_branch: str) -> int:
    pulls = paged(
        repository,
        "pulls",
        state="closed",
        sort="updated",
        direction="desc",
    )
    found = sorted(
        {
            pull["number"]
            for pull in pulls
            if pull.get("merged_at")
            and ((pull.get("head") or {}).get("ref")) == head_branch
            and ((pull.get("base") or {}).get("ref")) == base_branch
            and ((((pull.get("head") or {}).get("repo") or {}).get("full_name")))
            == repository
            and isinstance(pull.get("number"), int)
        }
    )
    if len(found) != 1:
        raise SystemExit(
            f"expected one merged PR for {head_branch}->{base_branch}; observed={found}"
        )
    return found[0]


def latest_decisive_reviews(reviews: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(reviews, key=lambda item: item.get("submitted_at") or ""):
        login = (review.get("user") or {}).get("login")
        state = review.get("state")
        if (
            isinstance(login, str)
            and login
            and state in DECISIVE_REVIEW_STATES
        ):
            latest[login] = review
    return latest


def review_threads(repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}"
    )
    value = command(
        "gh",
        "api",
        "graphql",
        "-f",
        f"query={query}",
        "-F",
        f"owner={owner}",
        "-F",
        f"name={name}",
        "-F",
        f"number={number}",
    )
    try:
        result = value["data"]["repository"]["pullRequest"]["reviewThreads"]
    except (KeyError, TypeError) as error:
        raise SystemExit("review-thread response malformed") from error
    if not isinstance(result, dict):
        raise SystemExit("review-thread response is not an object")
    return result


def commit_identity(repository: str, sha: str) -> tuple[str, list[str], bool]:
    value = rest(repository, f"commits/{sha}")
    tree = require_text(
        ((((value.get("commit") or {}).get("tree") or {}).get("sha"))),
        "commit tree",
    )
    parents = [
        require_text(item.get("sha"), "commit parent")
        for item in value.get("parents") or []
    ]
    verified = (
        (((value.get("commit") or {}).get("verification") or {}).get("verified"))
        is True
    )
    return tree, parents, verified


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
    required_reviewers = sorted(set(args.required_reviewer))
    required_workflows = sorted(set(args.required_workflow))
    if not required_reviewers:
        raise SystemExit("at least one required reviewer is required")
    if "current-head review admission" not in required_workflows:
        raise SystemExit("post-review current-head admission workflow is required")

    number = discover(
        args.repository,
        args.expected_head_branch,
        args.integration_branch,
    )
    pull = rest(args.repository, f"pulls/{number}")
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

    reviewed_head = require_text(head.get("sha"), "reviewed head")
    merge_commit = require_text(pull.get("merge_commit_sha"), "merge commit")
    base_commit = require_text(base.get("sha"), "base commit")
    author = require_text((pull.get("user") or {}).get("login"), "PR author")
    marker = f"<!-- current-head-review-admission:{reviewed_head} -->"
    if marker not in (pull.get("body") or ""):
        raise SystemExit("merged predecessor lacks exact-head admission marker")

    reviews = paged(args.repository, f"pulls/{number}/reviews")
    latest = latest_decisive_reviews(reviews)
    waiting = []
    for login in required_reviewers:
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

    threads = review_threads(args.repository, number)
    if ((threads.get("pageInfo") or {}).get("hasNextPage")) is not False:
        raise SystemExit("review threads exceed bounded verifier")
    nodes = threads.get("nodes") or []
    if not isinstance(nodes, list):
        raise SystemExit("review-thread nodes are not an array")
    if any(not item.get("isResolved") for item in nodes):
        raise SystemExit("merged predecessor retained unresolved review threads")

    runs = paged(
        args.repository,
        "actions/runs",
        key="workflow_runs",
        event="pull_request",
        head_sha=reviewed_head,
    )
    latest_runs: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: item.get("id") or 0):
        name = run.get("name")
        if isinstance(name, str):
            latest_runs[name] = run
    missing = sorted(set(required_workflows) - set(latest_runs))
    if missing:
        raise SystemExit("missing workflow families: " + ", ".join(missing))
    bad = []
    for name in required_workflows:
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
    integration = rest(args.repository, f"branches/{encoded}")
    integration_head = require_text(
        ((integration.get("commit") or {}).get("sha")),
        "integration head",
    )
    if integration_head != merge_commit:
        raise SystemExit(
            f"integration head {integration_head} != merge commit {merge_commit}"
        )

    head_tree, _, _ = commit_identity(args.repository, reviewed_head)
    merge_tree, parents, verified = commit_identity(args.repository, merge_commit)
    if not verified:
        raise SystemExit("merge commit is not GitHub verified")
    if parents != [base_commit, reviewed_head]:
        raise SystemExit(
            f"ordered merge parents mismatch: observed={parents} "
            f"expected={[base_commit, reviewed_head]}"
        )
    if merge_tree != head_tree:
        raise SystemExit(
            f"merge tree {merge_tree} != reviewed head tree {head_tree}"
        )

    result = {
        "repository": args.repository,
        "pull_request": number,
        "base_branch": args.integration_branch,
        "base_commit": base_commit,
        "reviewed_head": reviewed_head,
        "reviewed_tree": head_tree,
        "merge_commit": merge_commit,
        "merge_tree": merge_tree,
        "ordered_merge_parents": parents,
        "required_reviewers": required_reviewers,
        "required_workflows": required_workflows,
        "administrator_bypass": False,
        "authority_effect": "NONE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
