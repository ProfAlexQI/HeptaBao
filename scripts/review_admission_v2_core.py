#!/usr/bin/env python3
"""Fail-closed current-head repository-change review admission.

This module deliberately does not issue qualification, compatibility, release, migration,
or production authority. It validates a repository-change review packet only.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Callable, Iterable

SCHEMA = "heptabao.current-head-review-admission.v2"
REQUIRED_REVIEWERS = ("ProfHepta", "Tomasrgbsf")
REQUIRED_CODEOWNERS = ("ProfHepta",)
ALLOWED_PERMISSIONS = frozenset({"write", "maintain", "admin"})
DECISIVE_REVIEW_STATES = frozenset({"APPROVED", "CHANGES_REQUESTED", "DISMISSED"})
REQUIRED_WORKFLOWS = (
    "HeptaBao V1.4.7 post-merge truth and external admission",
    "HeptaBao V1.4.6 authoritative recovery closure",
    "plan-v1.4.5-security-invariant-closure",
    "plan-v1.4.4-module-documentation",
)
ANY_MARKER_RE = re.compile(r"<!--\s*current-head-review-admission:[^>]*-->")
DIGEST_MARKER_RE = re.compile(
    r"^<!-- current-head-review-admission:v2:([0-9a-f]{64}) -->$"
)


class AdmissionError(ValueError):
    """Raised when repository-change review admission must fail closed."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def parse_time(value: Any, label: str) -> datetime:
    require(isinstance(value, str) and value, f"missing {label}")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise AdmissionError(f"invalid {label}: {value!r}") from error
    require(parsed.tzinfo is not None, f"{label} must be timezone-aware")
    return parsed.astimezone(timezone.utc)


def canonical_json(value: Any) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
        + "\n"
    ).encode("utf-8")


def sha256_hex(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def latest_decisive_reviews(
    reviews: Iterable[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Reduce each user's history to the latest opinionated platform decision.

    COMMENTED and PENDING cannot erase APPROVED or CHANGES_REQUESTED. A DISMISSED
    review remains decisive until that reviewer submits a later opinionated review.
    """
    ordered = sorted(
        reviews,
        key=lambda item: (
            item.get("submitted_at") or "",
            int(item.get("id") or 0),
        ),
    )
    latest: dict[str, dict[str, Any]] = {}
    for review in ordered:
        user = (review.get("user") or {}).get("login")
        state = review.get("state")
        if isinstance(user, str) and user and state in DECISIVE_REVIEW_STATES:
            latest[user] = review
    return latest


def collect_pages(
    fetch_page: Callable[[int, int], Any],
    *,
    key: str | None = None,
    page_size: int = 100,
    maximum_pages: int = 100,
) -> list[dict[str, Any]]:
    """Collect REST pages into one list without adjacent-JSON ambiguity."""
    output: list[dict[str, Any]] = []
    for page in range(1, maximum_pages + 1):
        payload = fetch_page(page, page_size)
        values = payload.get(key) if key is not None and isinstance(payload, dict) else payload
        require(isinstance(values, list), "paginated response is not an array")
        require(
            all(isinstance(item, dict) for item in values),
            "paginated response contains a non-object item",
        )
        output.extend(values)
        if len(values) < page_size:
            return output
    raise AdmissionError("pagination exceeded bounded maximum")


def global_codeowners(content: str) -> set[str]:
    owners: set[str] = set()
    for raw_line in content.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        if not line:
            continue
        fields = line.split()
        if fields and fields[0] == "*":
            owners.update(field[1:] for field in fields[1:] if field.startswith("@"))
    return {owner.removeprefix("@") for owner in owners}


def commit_identity(value: dict[str, Any], label: str) -> dict[str, Any]:
    commit = value.get("commit") or {}
    tree = commit.get("tree") or {}
    verification = commit.get("verification") or {}
    parents = value.get("parents") or []
    result = {
        "sha": value.get("sha"),
        "tree": tree.get("sha"),
        "parents": [parent.get("sha") for parent in parents],
        "verified": verification.get("verified") is True,
        "author": (value.get("author") or {}).get("login"),
        "committer": (value.get("committer") or {}).get("login"),
    }
    require(isinstance(result["sha"], str) and result["sha"], f"missing {label} sha")
    require(isinstance(result["tree"], str) and result["tree"], f"missing {label} tree")
    require(all(isinstance(item, str) and item for item in result["parents"]), f"invalid {label} parents")
    return result


def select_technical_runs(
    runs: Iterable[dict[str, Any]],
    head_sha: str,
) -> tuple[list[dict[str, Any]], datetime]:
    latest: dict[str, dict[str, Any]] = {}
    for run in sorted(runs, key=lambda item: int(item.get("id") or 0)):
        name = run.get("name")
        if name in REQUIRED_WORKFLOWS and run.get("head_sha") == head_sha:
            latest[str(name)] = run
    missing = sorted(set(REQUIRED_WORKFLOWS) - set(latest))
    require(not missing, f"missing current-head technical workflow families: {missing}")
    packet: list[dict[str, Any]] = []
    completed_times: list[datetime] = []
    for name in REQUIRED_WORKFLOWS:
        run = latest[name]
        require(run.get("event") == "pull_request", f"{name}: event is not pull_request")
        require(run.get("status") == "completed", f"{name}: run is not terminal")
        require(run.get("conclusion") == "success", f"{name}: run did not succeed")
        updated_at = run.get("updated_at") or run.get("run_started_at")
        completed = parse_time(updated_at, f"{name} completion time")
        completed_times.append(completed)
        packet.append(
            {
                "id": int(run.get("id") or 0),
                "name": name,
                "head_sha": head_sha,
                "event": "pull_request",
                "status": "completed",
                "conclusion": "success",
                "updated_at": completed.isoformat().replace("+00:00", "Z"),
            }
        )
    return packet, max(completed_times)


def marker_for_digest(digest: str) -> str:
    require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, "invalid admission digest")
    return f"<!-- current-head-review-admission:v2:{digest} -->"


def evaluate_snapshot(
    snapshot: dict[str, Any],
    *,
    require_marker: bool = True,
) -> dict[str, Any]:
    repository = snapshot.get("repository")
    pull = snapshot.get("pull_request") or {}
    head = pull.get("head") or {}
    base = pull.get("base") or {}
    head_repo = head.get("repo") or {}

    require(isinstance(repository, str) and "/" in repository, "invalid repository")
    require(pull.get("state") == "open", "pull request is not open")
    require(pull.get("draft") is False, "pull request is draft")
    require(pull.get("mergeable") is True, "pull request is not currently mergeable")
    require(head_repo.get("full_name") == repository, "cross-repository head is not admitted")
    pr_number = pull.get("number")
    require(isinstance(pr_number, int) and pr_number > 0, "invalid pull request number")
    author = (pull.get("user") or {}).get("login")
    require(isinstance(author, str) and author, "missing pull request author")
    head_sha = head.get("sha")
    base_sha = base.get("sha")
    prospective_sha = pull.get("merge_commit_sha")
    for value, label in (
        (head_sha, "head sha"),
        (base_sha, "base sha"),
        (prospective_sha, "prospective merge sha"),
    ):
        require(isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40}", value) is not None, f"invalid {label}")

    event_head = snapshot.get("event_head_sha")
    event_base = snapshot.get("event_base_sha")
    if event_head is not None:
        require(event_head == head_sha, "event head differs from live head")
    if event_base is not None:
        require(event_base == base_sha, "event base differs from live base")

    head_commit = commit_identity(snapshot.get("head_commit") or {}, "head commit")
    prospective = commit_identity(snapshot.get("prospective_commit") or {}, "prospective merge")
    require(head_commit["sha"] == head_sha, "head commit object mismatch")
    require(prospective["sha"] == prospective_sha, "prospective merge object mismatch")
    require(prospective["verified"], "prospective merge is not GitHub verified")
    require(prospective["parents"] == [base_sha, head_sha], "prospective merge parents are not ordered base/head")
    require(prospective["tree"] == head_commit["tree"], "prospective merge tree differs from reviewed head tree")

    technical_runs, technical_completed_at = select_technical_runs(
        snapshot.get("workflow_runs") or [],
        str(head_sha),
    )
    decisions = latest_decisive_reviews(snapshot.get("reviews") or [])

    permissions = snapshot.get("permissions") or {}
    require(isinstance(permissions, dict), "permissions snapshot is malformed")
    codeowners_content = snapshot.get("codeowners_content")
    codeowners_sha = snapshot.get("codeowners_sha")
    require(isinstance(codeowners_content, str), "CODEOWNERS content missing")
    require(isinstance(codeowners_sha, str) and codeowners_sha, "CODEOWNERS blob sha missing")
    owners = global_codeowners(codeowners_content)
    for reviewer in REQUIRED_CODEOWNERS:
        require(reviewer in owners, f"required global CODEOWNER is absent: {reviewer}")

    conflicted_accounts = {
        account
        for account in (
            author,
            head_commit.get("author"),
            head_commit.get("committer"),
        )
        if isinstance(account, str) and account
    }
    current_head_changes = sorted(
        user
        for user, review in decisions.items()
        if review.get("commit_id") == head_sha
        and review.get("state") == "CHANGES_REQUESTED"
    )
    require(not current_head_changes, f"current-head changes requested by: {current_head_changes}")

    reviewer_packet: list[dict[str, Any]] = []
    for reviewer in REQUIRED_REVIEWERS:
        permission = permissions.get(reviewer)
        require(permission in ALLOWED_PERMISSIONS, f"{reviewer}: live permission is not write-or-higher")
        require(reviewer not in conflicted_accounts, f"{reviewer}: conflicts with PR author or final commit actor")
        review = decisions.get(reviewer)
        require(review is not None, f"{reviewer}: no decisive review")
        require(review.get("state") == "APPROVED", f"{reviewer}: latest decisive review is not APPROVED")
        require(review.get("commit_id") == head_sha, f"{reviewer}: approval is not bound to current head")
        submitted_at = parse_time(review.get("submitted_at"), f"{reviewer} approval time")
        require(submitted_at > technical_completed_at, f"{reviewer}: approval predates technical packet completion")
        reviewer_packet.append(
            {
                "login": reviewer,
                "permission": permission,
                "codeowner": reviewer in owners,
                "review_id": int(review.get("id") or 0),
                "state": "APPROVED",
                "commit_id": head_sha,
                "submitted_at": submitted_at.isoformat().replace("+00:00", "Z"),
            }
        )

    decision_packet = []
    for user, review in sorted(decisions.items()):
        decision_packet.append(
            {
                "login": user,
                "review_id": int(review.get("id") or 0),
                "state": review.get("state"),
                "commit_id": review.get("commit_id"),
                "submitted_at": review.get("submitted_at"),
            }
        )

    packet = {
        "schema": SCHEMA,
        "repository": repository,
        "pull_request": pr_number,
        "base_sha": base_sha,
        "head_sha": head_sha,
        "head_tree": head_commit["tree"],
        "prospective_merge_sha": prospective_sha,
        "prospective_merge_tree": prospective["tree"],
        "technical_completed_at": technical_completed_at.isoformat().replace("+00:00", "Z"),
        "technical_runs": technical_runs,
        "required_reviewers": reviewer_packet,
        "effective_decisions": decision_packet,
        "codeowners_blob_sha": codeowners_sha,
        "global_codeowners": sorted(owners),
        "conflicted_accounts": sorted(conflicted_accounts),
        "claims": {
            "qualification": False,
            "compatibility_claim": False,
            "production_authority": False,
            "migration_authority": False,
            "release_authority": False,
            "authority_effect": "NONE",
        },
    }
    digest = sha256_hex(canonical_json(packet))
    expected_marker = marker_for_digest(digest)
    body = pull.get("body") or ""
    markers = ANY_MARKER_RE.findall(body)
    if require_marker:
        require(markers == [expected_marker], f"body must contain exactly the current expected marker: {expected_marker}")

    return {
        "schema": SCHEMA,
        "packet_sha256": digest,
        "expected_marker": expected_marker,
        "packet": packet,
        "claims": packet["claims"],
    }
