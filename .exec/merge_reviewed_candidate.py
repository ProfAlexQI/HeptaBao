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


def rest(repository: str, endpoint: str) -> Any:
    return command("gh", "api", f"repos/{repository}/{endpoint}")


def require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value or value == "null":
        raise SystemExit(f"missing {label}")
    return value


def discover_open_pull(repository: str, head_branch: str, base_branch: str) -> int:
    found: list[int] = []
    for page in range(1, 101):
        query = urllib.parse.urlencode(
            {
                "state": "open",
                "per_page": 100,
                "page": page,
                "sort": "updated",
                "direction": "desc",
            }
        )
        pulls = rest(repository, f"pulls?{query}")
        if not isinstance(pulls, list):
            raise SystemExit("open pull discovery response is not an array")
        for pull in pulls:
            head = pull.get("head") or {}
            base = pull.get("base") or {}
            if (
                head.get("ref") == head_branch
                and base.get("ref") == base_branch
                and ((head.get("repo") or {}).get("full_name")) == repository
                and isinstance(pull.get("number"), int)
            ):
                found.append(pull["number"])
        if len(pulls) < 100:
            break
    else:
        raise SystemExit("open pull discovery exceeded bounded pagination")

    unique = sorted(set(found))
    if len(unique) != 1:
        raise SystemExit(
            f"expected one open PR for {head_branch}->{base_branch}; observed={unique}"
        )
    return unique[0]


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
    payload = command(
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
        result = payload["data"]["repository"]["pullRequest"]["reviewThreads"]
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


def write_result(path: Path | None, result: dict[str, Any]) -> None:
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if path is not None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded, encoding="utf-8")
    print(json.dumps(result, sort_keys=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--expected-head-branch", required=True)
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--required-reviewer", action="append", default=[])
    parser.add_argument("--required-workflow", action="append", default=[])
    parser.add_argument("--commit-title", required=True)
    parser.add_argument("--commit-message", required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.repository:
        raise SystemExit("repository is required")
    required_reviewers = sorted(set(args.required_reviewer))
    required_workflows = sorted(set(args.required_workflow))
    if not required_reviewers:
        raise SystemExit("at least one required reviewer is required")
    if "current-head review admission" not in required_workflows:
        raise SystemExit("post-review current-head admission workflow is required")

    number = discover_open_pull(
        args.repository,
        args.expected_head_branch,
        args.integration_branch,
    )
    pull = rest(args.repository, f"pulls/{number}")
    if pull.get("state") != "open" or pull.get("draft") is not False:
        raise SystemExit("candidate PR is not open and ready")
    if pull.get("mergeable") is not True:
        raise SystemExit(f"candidate PR mergeable is not true: {pull.get('mergeable')}")

    head = pull.get("head") or {}
    base = pull.get("base") or {}
    if head.get("ref") != args.expected_head_branch:
        raise SystemExit("candidate head branch mismatch")
    if base.get("ref") != args.integration_branch:
        raise SystemExit("candidate base branch mismatch")
    if ((head.get("repo") or {}).get("full_name")) != args.repository:
        raise SystemExit("candidate head repository mismatch")
    head_sha = require_text(head.get("sha"), "candidate head")
    base_sha = require_text(base.get("sha"), "candidate base")
    author = require_text((pull.get("user") or {}).get("login"), "PR author")
    body = pull.get("body") or ""
    marker = f"<!-- current-head-review-admission:{head_sha} -->"
    if marker not in body:
        raise SystemExit("exact-head post-review admission marker is absent")

    branch_ref = rest(
        args.repository,
        "git/ref/heads/" + urllib.parse.quote(args.expected_head_branch, safe="/"),
    )
    if (
        require_text((branch_ref.get("object") or {}).get("sha"), "candidate ref")
        != head_sha
    ):
        raise SystemExit("candidate branch moved away from PR head")

    reviews = rest(args.repository, f"pulls/{number}/reviews?per_page=100")
    if not isinstance(reviews, list):
        raise SystemExit("review response is not an array")
    latest = latest_decisive_reviews(reviews)
    waiting = []
    for login in required_reviewers:
        review = latest.get(login)
        if (
            not review
            or review.get("state") != "APPROVED"
            or review.get("commit_id") != head_sha
            or login == author
            or login.endswith("[bot]")
        ):
            waiting.append(login)
    if waiting:
        raise SystemExit("missing eligible exact-head approvals: " + ", ".join(waiting))
    blocking = sorted(
        login
        for login, review in latest.items()
        if review.get("commit_id") == head_sha
        and review.get("state") == "CHANGES_REQUESTED"
    )
    if blocking:
        raise SystemExit("current-head changes requested by: " + ", ".join(blocking))

    threads = review_threads(args.repository, number)
    page_info = threads.get("pageInfo") or {}
    if page_info.get("hasNextPage") is not False:
        raise SystemExit("review threads exceed bounded verifier")
    nodes = threads.get("nodes") or []
    if not isinstance(nodes, list):
        raise SystemExit("review-thread nodes are not an array")
    if any(not item.get("isResolved") for item in nodes):
        raise SystemExit("candidate has unresolved review threads")

    query = urllib.parse.urlencode(
        {"event": "pull_request", "head_sha": head_sha, "per_page": 100}
    )
    payload = rest(args.repository, f"actions/runs?{query}")
    runs = payload.get("workflow_runs")
    if not isinstance(runs, list):
        raise SystemExit("workflow response is not an array")
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
            run.get("head_sha") != head_sha
            or run.get("status") != "completed"
            or run.get("conclusion") != "success"
        ):
            bad.append(
                f"{name}:{run.get('head_sha')}:{run.get('status')}:{run.get('conclusion')}"
            )
    if bad:
        raise SystemExit("workflow admission failed: " + "; ".join(bad))

    head_tree, _, _ = commit_identity(args.repository, head_sha)
    prospective = require_text(pull.get("merge_commit_sha"), "prospective merge")
    prospective_tree, prospective_parents, prospective_verified = commit_identity(
        args.repository,
        prospective,
    )
    if not prospective_verified:
        raise SystemExit("prospective merge is not GitHub verified")
    if prospective_parents != [base_sha, head_sha]:
        raise SystemExit(
            f"prospective parents mismatch: {prospective_parents} != {[base_sha, head_sha]}"
        )
    if prospective_tree != head_tree:
        raise SystemExit(
            f"prospective tree {prospective_tree} != reviewed head tree {head_tree}"
        )

    live = rest(args.repository, f"pulls/{number}")
    live_head = require_text((live.get("head") or {}).get("sha"), "live head")
    live_base = require_text((live.get("base") or {}).get("sha"), "live base")
    live_prospective = require_text(
        live.get("merge_commit_sha"),
        "live prospective merge",
    )
    if (
        live.get("state") != "open"
        or live.get("draft") is not False
        or live_head != head_sha
        or live_base != base_sha
        or live_prospective != prospective
    ):
        raise SystemExit("candidate tuple changed before merge")
    encoded_base = urllib.parse.quote(args.integration_branch, safe="")
    integration = rest(args.repository, f"branches/{encoded_base}")
    if (
        require_text((integration.get("commit") or {}).get("sha"), "integration head")
        != base_sha
    ):
        raise SystemExit("integration branch moved before merge")

    premerge = {
        "repository": args.repository,
        "pull_request": number,
        "base_branch": args.integration_branch,
        "base_commit": base_sha,
        "reviewed_head": head_sha,
        "reviewed_tree": head_tree,
        "prospective_merge": prospective,
        "required_reviewers": required_reviewers,
        "required_workflows": required_workflows,
        "administrator_bypass": False,
        "authority_effect": "NONE",
    }
    if args.dry_run:
        premerge["mode"] = "DRY_RUN_PREMERGE_VALIDATED"
        write_result(args.output, premerge)
        return 0

    merged = command(
        "gh",
        "api",
        "-X",
        "PUT",
        f"repos/{args.repository}/pulls/{number}/merge",
        "-f",
        f"sha={head_sha}",
        "-f",
        "merge_method=merge",
        "-f",
        f"commit_title={args.commit_title}",
        "-f",
        f"commit_message={args.commit_message}",
    )
    if merged.get("merged") is not True:
        raise SystemExit(f"GitHub merge rejected candidate: {merged}")
    merge_sha = require_text(merged.get("sha"), "final merge commit")

    integration = rest(args.repository, f"branches/{encoded_base}")
    if (
        require_text(
            (integration.get("commit") or {}).get("sha"),
            "post-merge integration head",
        )
        != merge_sha
    ):
        raise SystemExit("integration readback does not equal final merge commit")
    final_tree, final_parents, final_verified = commit_identity(
        args.repository,
        merge_sha,
    )
    if not final_verified:
        raise SystemExit("final merge commit is not GitHub verified")
    if final_parents != [base_sha, head_sha]:
        raise SystemExit(
            f"final merge parents mismatch: {final_parents} != {[base_sha, head_sha]}"
        )
    if final_tree != head_tree:
        raise SystemExit(f"final merge tree {final_tree} != reviewed head tree {head_tree}")

    result = {
        **premerge,
        "final_merge": merge_sha,
        "mode": "ORDINARY_REVIEWED_MERGE_COMPLETE",
    }
    write_result(args.output, result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
