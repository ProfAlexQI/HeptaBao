from __future__ import annotations

import importlib.util
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "admission", ROOT / "scripts/review_admission_v2_core.py"
)
assert SPEC and SPEC.loader
admission = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(admission)

HEAD = "a" * 40
BASE = "b" * 40
MERGE = "c" * 40
TREE = "d" * 40


def iso(offset: int) -> str:
    value = datetime(2026, 9, 3, tzinfo=timezone.utc) + timedelta(minutes=offset)
    return value.isoformat().replace("+00:00", "Z")


def review(identifier: int, login: str, state: str, commit: str = HEAD, minute: int = 10):
    return {
        "id": identifier,
        "state": state,
        "commit_id": commit,
        "submitted_at": iso(minute),
        "user": {"login": login},
    }


def run(identifier: int, name: str, *, conclusion: str = "success", minute: int = 5):
    return {
        "id": identifier,
        "name": name,
        "head_sha": HEAD,
        "event": "pull_request",
        "status": "completed",
        "conclusion": conclusion,
        "updated_at": iso(minute),
    }


def snapshot() -> dict:
    value = {
        "repository": "TrillionniumFoundation/HeptaBao",
        "pull_request": {
            "number": 63,
            "state": "open",
            "draft": False,
            "mergeable": True,
            "body": "review packet",
            "merge_commit_sha": MERGE,
            "user": {"login": "Franksudoman"},
            "head": {
                "sha": HEAD,
                "repo": {"full_name": "TrillionniumFoundation/HeptaBao"},
            },
            "base": {"sha": BASE},
        },
        "event_head_sha": HEAD,
        "event_base_sha": BASE,
        "head_commit": {
            "sha": HEAD,
            "commit": {
                "tree": {"sha": TREE},
                "verification": {"verified": False},
            },
            "parents": [{"sha": "e" * 40}],
            "author": {"login": "Franksudoman"},
            "committer": {"login": "Franksudoman"},
        },
        "prospective_commit": {
            "sha": MERGE,
            "commit": {
                "tree": {"sha": TREE},
                "verification": {"verified": True},
            },
            "parents": [{"sha": BASE}, {"sha": HEAD}],
            "author": {"login": "Franksudoman"},
            "committer": {"login": "web-flow"},
        },
        "workflow_runs": [
            run(index, name)
            for index, name in enumerate(admission.REQUIRED_WORKFLOWS, 100)
        ],
        "reviews": [
            review(1, "ProfHepta", "APPROVED", minute=10),
            review(2, "Tomasrgbsf", "APPROVED", minute=11),
        ],
        "permissions": {"ProfHepta": "admin", "Tomasrgbsf": "admin"},
        "codeowners_sha": "f" * 40,
        "codeowners_content": "* @ProfHepta\n/docs/ @ProfHepta\n",
    }
    marker = admission.evaluate_snapshot(value, require_marker=False)["expected_marker"]
    value["pull_request"]["body"] += "\n\n" + marker
    return value


class AdmissionTests(unittest.TestCase):
    def assertDenied(self, value: dict, fragment: str) -> None:
        with self.assertRaises(admission.AdmissionError) as raised:
            admission.evaluate_snapshot(value)
        self.assertIn(fragment, str(raised.exception))

    def test_valid_packet_is_repository_scope_only(self) -> None:
        result = admission.evaluate_snapshot(snapshot())
        self.assertRegex(result["expected_marker"], r"^<!-- current-head-review-admission:v2:[0-9a-f]{64} -->$")
        self.assertFalse(result["claims"]["qualification"])
        self.assertEqual("NONE", result["claims"]["authority_effect"])
        reviewers = result["packet"]["required_reviewers"]
        self.assertEqual(["ProfHepta", "Tomasrgbsf"], [item["login"] for item in reviewers])
        self.assertTrue(reviewers[0]["codeowner"])
        self.assertFalse(reviewers[1]["codeowner"])

    def test_missing_marker_fails_instead_of_skipping(self) -> None:
        value = snapshot()
        value["pull_request"]["body"] = "no marker"
        self.assertDenied(value, "exactly the current expected marker")

    def test_stale_and_multiple_markers_fail(self) -> None:
        value = snapshot()
        value["pull_request"]["body"] += "\n<!-- current-head-review-admission:v2:" + "0" * 64 + " -->"
        self.assertDenied(value, "exactly the current expected marker")

    def test_comment_does_not_erase_change_request(self) -> None:
        value = snapshot()
        value["reviews"] = [
            review(1, "ProfHepta", "CHANGES_REQUESTED", minute=8),
            review(2, "ProfHepta", "COMMENTED", minute=9),
            review(3, "Tomasrgbsf", "APPROVED", minute=10),
        ]
        self.assertDenied(value, "current-head changes requested")

    def test_comment_does_not_erase_approval(self) -> None:
        value = snapshot()
        value["reviews"] = [
            review(1, "ProfHepta", "APPROVED", minute=10),
            review(2, "ProfHepta", "COMMENTED", minute=12),
            review(3, "Tomasrgbsf", "APPROVED", minute=11),
        ]
        expected = admission.evaluate_snapshot(value, require_marker=False)["expected_marker"]
        value["pull_request"]["body"] = expected
        self.assertEqual(expected, admission.evaluate_snapshot(value)["expected_marker"])

    def test_dismissal_invalidates_marker_and_reapproval_restores(self) -> None:
        value = snapshot()
        approved_marker = admission.evaluate_snapshot(value)["expected_marker"]
        value["reviews"][0]["state"] = "DISMISSED"
        self.assertDenied(value, "latest decisive review is not APPROVED")
        value["reviews"].append(review(3, "ProfHepta", "APPROVED", minute=13))
        new_marker = admission.evaluate_snapshot(value, require_marker=False)["expected_marker"]
        self.assertNotEqual(approved_marker, new_marker)
        value["pull_request"]["body"] = new_marker
        self.assertEqual(new_marker, admission.evaluate_snapshot(value)["expected_marker"])

    def test_old_head_and_pretechnical_approvals_fail(self) -> None:
        value = snapshot()
        value["reviews"][0]["commit_id"] = "9" * 40
        self.assertDenied(value, "approval is not bound to current head")
        value = snapshot()
        value["reviews"][0]["submitted_at"] = iso(4)
        self.assertDenied(value, "predates technical packet completion")

    def test_noneligible_or_conflicted_reviewer_fails(self) -> None:
        value = snapshot()
        value["permissions"]["Tomasrgbsf"] = "read"
        self.assertDenied(value, "live permission is not write-or-higher")
        value = snapshot()
        value["pull_request"]["user"]["login"] = "ProfHepta"
        self.assertDenied(value, "conflicts with PR author or final commit actor")

    def test_missing_global_codeowner_fails(self) -> None:
        value = snapshot()
        value["codeowners_content"] = "/docs/ @ProfHepta\n"
        self.assertDenied(value, "required global CODEOWNER is absent")

    def test_technical_failure_and_movement_fail(self) -> None:
        value = snapshot()
        value["workflow_runs"][0]["conclusion"] = "failure"
        self.assertDenied(value, "did not succeed")
        value = snapshot()
        value["event_head_sha"] = "8" * 40
        self.assertDenied(value, "event head differs from live head")
        value = snapshot()
        value["prospective_commit"]["commit"]["tree"]["sha"] = "7" * 40
        self.assertDenied(value, "tree differs")
        value = snapshot()
        value["prospective_commit"]["commit"]["verification"]["verified"] = False
        self.assertDenied(value, "not GitHub verified")

    def test_decisive_reducer_orders_dismissal_and_reapproval(self) -> None:
        values = [
            review(1, "r", "APPROVED", minute=1),
            review(2, "r", "COMMENTED", minute=2),
            review(3, "r", "DISMISSED", minute=3),
            review(4, "r", "APPROVED", minute=4),
        ]
        self.assertEqual("APPROVED", admission.latest_decisive_reviews(values)["r"]["state"])

    def test_paginated_histories_are_flattened(self) -> None:
        first = [{"id": item} for item in range(100)]
        second = [{"id": 100}]
        calls: list[int] = []

        def fetch(page: int, per_page: int):
            self.assertEqual(100, per_page)
            calls.append(page)
            return first if page == 1 else second

        result = admission.collect_pages(fetch)
        self.assertEqual(101, len(result))
        self.assertEqual([1, 2], calls)


if __name__ == "__main__":
    unittest.main()
