#!/usr/bin/env python3
"""One-shot ordinary merge controller for a V2-reviewed HeptaBao candidate."""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import urllib.parse
from pathlib import Path
from typing import Any

SCHEMA = "heptabao.current-head-review-admission.v2"
REQUIRED_REVIEWERS = ("ProfHepta", "Tomasrgbsf")
REQUIRED_TECHNICAL = (
    "HeptaBao V1.4.7 post-merge truth and external admission",
    "HeptaBao V1.4.6 authoritative recovery closure",
    "plan-v1.4.5-security-invariant-closure",
    "plan-v1.4.4-module-documentation",
)
REVIEW_SCRIPTS = (
    "scripts/review_admission_v2_core.py",
    "scripts/current_head_review_admission_v2.py",
    "scripts/review_admission_v2_archive.py",
)


class MergeDenied(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MergeDenied(message)


def command(*args: str) -> Any:
    output = subprocess.check_output(args, text=True)
    return json.loads(output)


def api(repository: str, endpoint: str, *, method: str = "GET", fields: dict[str, Any] | None = None) -> Any:
    args = ["gh", "api", "--method", method, f"repos/{repository}/{endpoint}"]
    for name, value in (fields or {}).items():
        args.extend(["-f", f"{name}={value}"])
    return command(*args)


def paged(repository: str, endpoint: str, *, key: str | None = None, params: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for page in range(1, 101):
        value = api(repository, endpoint, fields={**(params or {}), "page": page, "per_page": 100})
        items = value.get(key) if key is not None and isinstance(value, dict) else value
        require(isinstance(items, list), f"paged response is not an array: {endpoint}")
        require(all(isinstance(item, dict) for item in items), f"paged response contains non-object: {endpoint}")
        output.extend(items)
        if len(items) < 100:
            return output
    raise MergeDenied(f"pagination exceeded bounded maximum: {endpoint}")


def discover_open_pr(repository: str, head_branch: str, base_branch: str) -> int:
    pulls = paged(repository, "pulls", params={"state": "open", "sort": "updated", "direction": "desc"})
    found = sorted({
        pull["number"]
        for pull in pulls
        if isinstance(pull.get("number"), int)
        and ((pull.get("head") or {}).get("ref")) == head_branch
        and ((pull.get("base") or {}).get("ref")) == base_branch
        and ((((pull.get("head") or {}).get("repo") or {}).get("full_name"))) == repository
    })
    require(len(found) == 1, f"expected one open candidate PR, observed={found}")
    return found[0]


def download_review_scripts(repository: str, head_sha: str, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for path in REVIEW_SCRIPTS:
        value = api(repository, f"contents/{path}", fields={"ref": head_sha})
        encoded = value.get("content")
        require(isinstance(encoded, str), f"candidate review script missing: {path}")
        try:
            raw = base64.b64decode(encoded)
        except ValueError as error:
            raise MergeDenied(f"candidate review script is not valid base64: {path}") from error
        destination = directory / Path(path).name
        destination.write_bytes(raw)
        compile(raw, path, "exec")


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
    }
    require(result["sha"] == sha, f"commit object mismatch: {sha}")
    require(isinstance(result["tree"], str) and result["tree"], f"commit tree missing: {sha}")
    require(all(isinstance(parent, str) and parent for parent in result["parents"]), f"invalid commit parents: {sha}")
    return result


def review_threads(repository: str, number: int) -> dict[str, Any]:
    owner, name = repository.split("/", 1)
    query = (
        "query($owner:String!,$name:String!,$number:Int!){"
        "repository(owner:$owner,name:$name){pullRequest(number:$number){"
        "reviewThreads(first:100){nodes{isResolved}pageInfo{hasNextPage}}}}}"
    )
    value = command(
        "gh", "api", "graphql",
        "-f", f"query={query}",
        "-F", f"owner={owner}",
        "-F", f"name={name}",
        "-F", f"number={number}",
    )
    try:
        result = value["data"]["repository"]["pullRequest"]["reviewThreads"]
    except (KeyError, TypeError) as error:
        raise MergeDenied("review-thread response malformed") from error
    require(isinstance(result, dict), "review-thread response is not an object")
    return result


def validate_packet(result: dict[str, Any], pull: dict[str, Any]) -> None:
    require(result.get("schema") == SCHEMA, "review packet schema mismatch")
    packet = result.get("packet") or {}
    claims = result.get("claims") or {}
    head_sha = ((pull.get("head") or {}).get("sha"))
    base_sha = ((pull.get("base") or {}).get("sha"))
    prospective = pull.get("merge_commit_sha")
    require(packet.get("head_sha") == head_sha, "review packet head mismatch")
    require(packet.get("base_sha") == base_sha, "review packet base mismatch")
    require(packet.get("prospective_merge_sha") == prospective, "review packet prospective merge mismatch")
    reviewers = packet.get("required_reviewers") or []
    require([item.get("login") for item in reviewers] == list(REQUIRED_REVIEWERS), "review packet reviewer set mismatch")
    require(all(item.get("state") == "APPROVED" and item.get("commit_id") == head_sha for item in reviewers), "review packet lacks exact-head approvals")
    technical = packet.get("technical_runs") or []
    require([item.get("name") for item in technical] == list(REQUIRED_TECHNICAL), "review packet technical family mismatch")
    require(all(item.get("status") == "completed" and item.get("conclusion") == "success" for item in technical), "review packet contains unsuccessful technical run")
    require(claims == {
        "qualification": False,
        "compatibility_claim": False,
        "production_authority": False,
        "migration_authority": False,
        "release_authority": False,
        "authority_effect": "NONE",
    }, "review packet authority drift")
    marker = result.get("expected_marker")
    require(isinstance(marker, str) and (pull.get("body") or "").count(marker) == 1, "exact V2 marker is not uniquely present")


def latest_successful_admission(repository: str, head_sha: str) -> dict[str, Any]:
    runs = paged(
        repository,
        "actions/runs",
        key="workflow_runs",
        params={"event": "pull_request", "head_sha": head_sha},
    )
    matching = [run for run in runs if run.get("name") == "current-head review admission"]
    require(matching, "current-head review admission run is missing")
    latest = max(matching, key=lambda item: int(item.get("id") or 0))
    require(latest.get("head_sha") == head_sha, "review admission run head mismatch")
    require(latest.get("status") == "completed", "review admission run is not terminal")
    require(latest.get("conclusion") == "success", "review admission run did not succeed")
    return latest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--head-branch", required=True)
    parser.add_argument("--base-branch", required=True)
    parser.add_argument("--commit-title", required=True)
    parser.add_argument("--commit-message", required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    require(isinstance(args.repository, str) and "/" in args.repository, "repository is required")
    require(bool(os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")), "GitHub token is required")

    number = discover_open_pr(args.repository, args.head_branch, args.base_branch)
    pull = api(args.repository, f"pulls/{number}")
    require(pull.get("state") == "open" and pull.get("draft") is False, "candidate PR is not open and ready")
    require(pull.get("mergeable") is True, f"candidate PR mergeable is not true: {pull.get('mergeable')}")
    head_sha = ((pull.get("head") or {}).get("sha"))
    base_sha = ((pull.get("base") or {}).get("sha"))
    prospective_sha = pull.get("merge_commit_sha")
    require(isinstance(head_sha, str) and isinstance(base_sha, str) and isinstance(prospective_sha, str), "candidate tuple is incomplete")

    ref = api(args.repository, "git/ref/heads/" + urllib.parse.quote(args.head_branch, safe="/"))
    require(((ref.get("object") or {}).get("sha")) == head_sha, "candidate branch moved away from PR head")

    scripts = Path(os.environ.get("RUNNER_TEMP", "/tmp")) / "heptabao-review-v2"
    download_review_scripts(args.repository, head_sha, scripts)
    packet_path = scripts / "live-packet.json"
    subprocess.run(
        [
            sys.executable,
            str(scripts / "current_head_review_admission_v2.py"),
            "--repository", args.repository,
            "--pr", str(number),
            "--output", str(packet_path),
        ],
        check=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")},
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    validate_packet(packet, pull)
    admission_run = latest_successful_admission(args.repository, head_sha)

    threads = review_threads(args.repository, number)
    require(((threads.get("pageInfo") or {}).get("hasNextPage")) is False, "review threads exceed bounded verifier")
    nodes = threads.get("nodes") or []
    require(isinstance(nodes, list), "review-thread nodes are not an array")
    require(all(item.get("isResolved") is True for item in nodes), "candidate has unresolved review threads")

    head = commit_identity(args.repository, head_sha)
    prospective = commit_identity(args.repository, prospective_sha)
    require(prospective["verified"], "prospective merge is not GitHub verified")
    require(prospective["parents"] == [base_sha, head_sha], "prospective merge parents are not ordered base/head")
    require(prospective["tree"] == head["tree"], "prospective merge tree differs from reviewed head tree")

    live = api(args.repository, f"pulls/{number}")
    require(live.get("state") == "open" and live.get("draft") is False, "candidate changed state before merge")
    require(((live.get("head") or {}).get("sha")) == head_sha, "candidate head moved before merge")
    require(((live.get("base") or {}).get("sha")) == base_sha, "candidate base moved before merge")
    require(live.get("merge_commit_sha") == prospective_sha, "candidate prospective merge moved before merge")
    base_ref = api(args.repository, "git/ref/heads/" + urllib.parse.quote(args.base_branch, safe="/"))
    require(((base_ref.get("object") or {}).get("sha")) == base_sha, "base branch moved before merge")

    merged = api(
        args.repository,
        f"pulls/{number}/merge",
        method="PUT",
        fields={
            "sha": head_sha,
            "merge_method": "merge",
            "commit_title": args.commit_title,
            "commit_message": args.commit_message,
        },
    )
    require(merged.get("merged") is True, f"ordinary GitHub merge rejected: {merged}")
    final_sha = merged.get("sha")
    require(isinstance(final_sha, str), "final merge SHA missing")

    final_ref = api(args.repository, "git/ref/heads/" + urllib.parse.quote(args.base_branch, safe="/"))
    require(((final_ref.get("object") or {}).get("sha")) == final_sha, "integration readback differs from final merge")
    final = commit_identity(args.repository, final_sha)
    require(final["verified"], "final merge is not GitHub verified")
    require(final["parents"] == [base_sha, head_sha], "final merge parents are not ordered base/head")
    require(final["tree"] == head["tree"], "final merge tree differs from reviewed head tree")

    archive_path = scripts / "archived-packet.json"
    subprocess.run(
        [
            sys.executable,
            str(scripts / "review_admission_v2_archive.py"),
            "--repository", args.repository,
            "--pr", str(number),
            "--output", str(archive_path),
        ],
        check=True,
        env={**os.environ, "GH_TOKEN": os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN", "")},
    )
    archived = json.loads(archive_path.read_text(encoding="utf-8"))
    require(archived.get("packet_sha256") == packet.get("packet_sha256"), "post-merge packet digest differs from live packet")
    require(((archived.get("final_merge") or {}).get("final_merge_sha")) == final_sha, "archive verifier final merge mismatch")

    result = {
        "repository": args.repository,
        "pull_request": number,
        "base_branch": args.base_branch,
        "base_commit": base_sha,
        "reviewed_head": head_sha,
        "reviewed_tree": head["tree"],
        "prospective_merge": prospective_sha,
        "admission_run": int(admission_run.get("id") or 0),
        "packet_sha256": packet.get("packet_sha256"),
        "final_merge": final_sha,
        "administrator_bypass": False,
        "authority_effect": "NONE",
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except MergeDenied as error:
        raise SystemExit(f"REVIEWED_MERGE_DENIED: {error}") from error
