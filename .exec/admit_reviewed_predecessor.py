#!/usr/bin/env python3
"""Admit one exact reviewed predecessor merge for a successor materializer.

The V2 review packet is recomputed from the predecessor candidate itself. This
script adds version-specific workflow and approval timing checks; it never
creates qualification, compatibility, release, migration or production
authority.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

ALLOWED_PERMISSIONS = frozenset({"write", "maintain", "admin"})
DECISIVE_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
POST_REVIEW_WORKFLOW = "current-head review admission"
REVIEW_SCRIPTS = (
    "scripts/review_admission_v2_core.py",
    "scripts/current_head_review_admission_v2.py",
    "scripts/review_admission_v2_archive.py",
)
FALSE_CLAIMS = {
    "qualification": False,
    "compatibility_claim": False,
    "production_authority": False,
    "migration_authority": False,
    "release_authority": False,
    "authority_effect": "NONE",
}


class AdmissionDenied(RuntimeError):
    """Raised whenever predecessor admission must fail closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionDenied(message)


def command(*args: str, env: dict[str, str] | None = None) -> Any:
    output = subprocess.check_output(args, text=True, env=env)
    return json.loads(output)


def api(
    repository: str,
    endpoint: str,
    *,
    method: str = "GET",
    fields: dict[str, Any] | None = None,
) -> Any:
    args = ["gh", "api", "--method", method, f"repos/{repository}/{endpoint}"]
    for name, value in (fields or {}).items():
        args.extend(["-f", f"{name}={value}"])
    return command(*args)


def paged(
    repository: str,
    endpoint: str,
    *,
    key: str | None = None,
    params: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 101):
        payload = api(
            repository,
            endpoint,
            fields={**(params or {}), "page": page, "per_page": 100},
        )
        values = payload.get(key) if key is not None and isinstance(payload, dict) else payload
        require(isinstance(values, list), f"paged response is not an array: {endpoint}")
        require(
            all(isinstance(item, dict) for item in values),
            f"paged response contains a non-object: {endpoint}",
        )
        output.extend(values)
        if len(values) < 100:
            return output
    raise AdmissionDenied(f"pagination exceeded bounded maximum: {endpoint}")


def require_text(value: Any, label: str) -> str:
    require(isinstance(value, str) and bool(value) and value != "null", f"missing {label}")
    return str(value)


def parse_time(value: Any, label: str) -> datetime:
    require(isinstance(value, str) and bool(value), f"missing {label}")
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as error:
        raise AdmissionDenied(f"invalid {label}: {value!r}") from error
    require(parsed.tzinfo is not None, f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def discover_merged_pull(
    repository: str,
    head_branch: str,
    base_branch: str,
) -> int:
    pulls = paged(
        repository,
        "pulls",
        params={"state": "closed", "sort": "updated", "direction": "desc"},
    )
    matches = sorted(
        {
            int(pull["number"])
            for pull in pulls
            if isinstance(pull.get("number"), int)
            and pull.get("merged_at")
            and ((pull.get("head") or {}).get("ref")) == head_branch
            and ((pull.get("base") or {}).get("ref")) == base_branch
            and ((((pull.get("head") or {}).get("repo") or {}).get("full_name")))
            == repository
        }
    )
    require(
        len(matches) == 1,
        f"expected one merged predecessor PR for {head_branch}->{base_branch}; observed={matches}",
    )
    return matches[0]


def latest_decisive_reviews(
    reviews: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for review in sorted(
        reviews,
        key=lambda item: (
            item.get("submitted_at") or "",
            int(item.get("id") or 0),
        ),
    ):
        login = (review.get("user") or {}).get("login")
        state = review.get("state")
        if isinstance(login, str) and login and state in DECISIVE_REVIEW_STATES:
            latest[login] = review
    return latest


def commit_identity(repository: str, sha: str) -> dict[str, Any]:
    value = api(repository, f"commits/{sha}")
    commit = value.get("commit") or {}
    tree = commit.get("tree") or {}
    verification = commit.get("verification") or {}
    result = {
        "sha": value.get("sha"),
        "tree": tree.get("sha"),
        "parents": [(parent or {}).get("sha") for parent in value.get("parents") or []],
        "verified": verification.get("verified") is True,
        "author": (value.get("author") or {}).get("login"),
        "committer": (value.get("committer") or {}).get("login"),
    }
    require(result["sha"] == sha, f"commit object mismatch: {sha}")
    require(isinstance(result["tree"], str) and result["tree"], f"commit tree missing: {sha}")
    require(
        all(isinstance(parent, str) and parent for parent in result["parents"]),
        f"invalid commit parents: {sha}",
    )
    return result


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
        raise AdmissionDenied("review-thread response malformed") from error
    require(isinstance(result, dict), "review-thread response is not an object")
    return result


def select_workflow_runs(
    runs: Iterable[dict[str, Any]],
    required: list[str],
    head_sha: str,
) -> tuple[dict[str, dict[str, Any]], datetime, datetime]:
    latest: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: int(item.get("id") or 0)):
        name = run.get("name")
        if name in required and run.get("head_sha") == head_sha:
            latest[str(name)] = run
    missing = sorted(set(required) - set(latest))
    require(not missing, f"missing predecessor workflow families: {missing}")

    technical_times: list[datetime] = []
    all_times: list[datetime] = []
    for name in required:
        run = latest[name]
        require(run.get("event") == "pull_request", f"{name}: event is not pull_request")
        require(run.get("status") == "completed", f"{name}: run is not terminal")
        require(run.get("conclusion") == "success", f"{name}: run did not succeed")
        completed = parse_time(
            run.get("updated_at") or run.get("run_started_at"),
            f"{name} completion time",
        )
        all_times.append(completed)
        if name != POST_REVIEW_WORKFLOW:
            technical_times.append(completed)
    require(technical_times, "no predecessor technical workflow family was supplied")
    return latest, max(technical_times), max(all_times)


def download_review_scripts(
    repository: str,
    head_sha: str,
    directory: Path,
) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for source_path in REVIEW_SCRIPTS:
        value = api(repository, f"contents/{source_path}", fields={"ref": head_sha})
        encoded = value.get("content")
        require(isinstance(encoded, str), f"predecessor V2 review script missing: {source_path}")
        try:
            raw = base64.b64decode(encoded)
        except ValueError as error:
            raise AdmissionDenied(
                f"predecessor V2 review script has invalid encoding: {source_path}"
            ) from error
        destination = directory / Path(source_path).name
        destination.write_bytes(raw)
        compile(raw, source_path, "exec")


def run_archived_packet(
    repository: str,
    number: int,
    head_sha: str,
) -> dict[str, Any]:
    root = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / f"heptabao-predecessor-v2-{number}"
    download_review_scripts(repository, head_sha, root)
    output = root / "archived-review-packet.json"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    require(bool(token), "GitHub token is required")
    subprocess.run(
        [
            sys.executable,
            str(root / "review_admission_v2_archive.py"),
            "--repository",
            repository,
            "--pr",
            str(number),
            "--output",
            str(output),
        ],
        check=True,
        env={**os.environ, "GH_TOKEN": str(token)},
    )
    value = json.loads(output.read_text(encoding="utf-8"))
    require(isinstance(value, dict), "archived V2 packet is not an object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--pr", type=int, help="deprecated non-authoritative hint")
    parser.add_argument("--expected-head-branch", required=True)
    parser.add_argument("--integration-branch", required=True)
    parser.add_argument("--required-reviewer", action="append", default=[])
    parser.add_argument("--required-workflow", action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    repository = require_text(args.repository, "repository")
    reviewers = sorted(set(args.required_reviewer))
    workflows = list(dict.fromkeys(args.required_workflow))
    require(reviewers, "at least one required reviewer is required")
    require(POST_REVIEW_WORKFLOW in workflows, "current-head review admission is required")

    number = discover_merged_pull(
        repository,
        args.expected_head_branch,
        args.integration_branch,
    )
    pull = api(repository, f"pulls/{number}")
    require(pull.get("state") == "closed" and pull.get("merged") is True, f"PR #{number} is not merged")
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    require(head.get("ref") == args.expected_head_branch, "predecessor head branch mismatch")
    require(base.get("ref") == args.integration_branch, "predecessor base branch mismatch")
    require(((head.get("repo") or {}).get("full_name")) == repository, "predecessor head repository mismatch")

    head_sha = require_text(head.get("sha"), "reviewed head")
    base_sha = require_text(base.get("sha"), "base commit")
    merge_sha = require_text(pull.get("merge_commit_sha"), "final merge commit")
    author = require_text((pull.get("user") or {}).get("login"), "PR author")
    head_commit = commit_identity(repository, head_sha)
    final_merge = commit_identity(repository, merge_sha)
    require(final_merge["verified"], "final merge is not GitHub verified")
    require(final_merge["parents"] == [base_sha, head_sha], "final merge parents are not ordered base/head")
    require(final_merge["tree"] == head_commit["tree"], "final merge tree differs from reviewed head tree")

    encoded_branch = urllib.parse.quote(args.integration_branch, safe="")
    branch = api(repository, f"branches/{encoded_branch}")
    require(
        ((branch.get("commit") or {}).get("sha")) == merge_sha,
        "integration head does not equal predecessor merge commit",
    )

    reviews = paged(repository, f"pulls/{number}/reviews")
    decisions = latest_decisive_reviews(reviews)
    runs = paged(
        repository,
        "actions/runs",
        key="workflow_runs",
        params={"event": "pull_request", "head_sha": head_sha},
    )
    selected_runs, technical_completed_at, all_workflows_completed_at = select_workflow_runs(
        runs,
        workflows,
        head_sha,
    )

    conflicted = {
        account
        for account in (author, head_commit.get("author"), head_commit.get("committer"))
        if isinstance(account, str) and account
    }
    approval_times: list[datetime] = []
    reviewer_packet: list[dict[str, Any]] = []
    for reviewer in reviewers:
        permission_value = api(repository, f"collaborators/{reviewer}/permission")
        permission = permission_value.get("permission")
        require(permission in ALLOWED_PERMISSIONS, f"{reviewer}: permission is not write-or-higher")
        require(reviewer not in conflicted, f"{reviewer}: conflicts with predecessor source actor")
        decision = decisions.get(reviewer)
        require(decision is not None, f"{reviewer}: no decisive review")
        require(decision.get("state") == "APPROVED", f"{reviewer}: latest decisive review is not APPROVED")
        require(decision.get("commit_id") == head_sha, f"{reviewer}: approval is not bound to predecessor head")
        submitted_at = parse_time(decision.get("submitted_at"), f"{reviewer} approval time")
        require(
            submitted_at > technical_completed_at,
            f"{reviewer}: approval predates complete predecessor technical packet",
        )
        approval_times.append(submitted_at)
        reviewer_packet.append(
            {
                "login": reviewer,
                "permission": permission,
                "review_id": int(decision.get("id") or 0),
                "state": "APPROVED",
                "commit_id": head_sha,
                "submitted_at": submitted_at.isoformat().replace("+00:00", "Z"),
            }
        )

    current_changes = sorted(
        login
        for login, decision in decisions.items()
        if decision.get("commit_id") == head_sha
        and decision.get("state") == "CHANGES_REQUESTED"
    )
    require(not current_changes, f"current-head changes requested by: {current_changes}")
    admission_run = selected_runs[POST_REVIEW_WORKFLOW]
    admission_completed_at = parse_time(
        admission_run.get("updated_at") or admission_run.get("run_started_at"),
        "current-head review admission completion time",
    )
    require(
        admission_completed_at > max(approval_times),
        "current-head review admission did not complete after all approvals",
    )

    threads = review_threads(repository, number)
    require(((threads.get("pageInfo") or {}).get("hasNextPage")) is False, "review threads exceed bounded verifier")
    nodes = threads.get("nodes") or []
    require(isinstance(nodes, list), "review-thread nodes are not an array")
    require(all(item.get("isResolved") is True for item in nodes), "predecessor has unresolved review threads")

    archived = run_archived_packet(repository, number, head_sha)
    require(archived.get("schema") == "heptabao.current-head-review-admission.v2", "archived V2 schema mismatch")
    packet = archived.get("packet") or {}
    require(packet.get("head_sha") == head_sha, "archived V2 head mismatch")
    require(packet.get("base_sha") == base_sha, "archived V2 base mismatch")
    archived_final = archived.get("final_merge") or {}
    require(archived_final.get("final_merge_sha") == merge_sha, "archived V2 final merge mismatch")
    require(archived.get("claims") == FALSE_CLAIMS, "archived V2 authority drift")

    workflow_packet = []
    for name in workflows:
        run = selected_runs[name]
        workflow_packet.append(
            {
                "id": int(run.get("id") or 0),
                "name": name,
                "head_sha": head_sha,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "success",
                "updated_at": parse_time(
                    run.get("updated_at") or run.get("run_started_at"),
                    f"{name} completion time",
                ).isoformat().replace("+00:00", "Z"),
            }
        )

    result = {
        "schema": "heptabao.reviewed-predecessor-admission.v2",
        "repository": repository,
        "pull_request": number,
        "deprecated_pr_hint": args.pr,
        "base_branch": args.integration_branch,
        "base_commit": base_sha,
        "reviewed_head": head_sha,
        "reviewed_tree": head_commit["tree"],
        "merge_commit": merge_sha,
        "merge_tree": final_merge["tree"],
        "ordered_merge_parents": final_merge["parents"],
        "technical_completed_at": technical_completed_at.isoformat().replace("+00:00", "Z"),
        "all_workflows_completed_at": all_workflows_completed_at.isoformat().replace("+00:00", "Z"),
        "required_reviewers": reviewer_packet,
        "required_workflows": workflow_packet,
        "review_packet_sha256": archived.get("packet_sha256"),
        "administrator_bypass": False,
        "claims": FALSE_CLAIMS,
        "authority_effect": "NONE",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except AdmissionDenied as error:
        raise SystemExit(f"PREDECESSOR_ADMISSION_DENIED: {error}") from error
