from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CORE_SPEC = importlib.util.spec_from_file_location("review_core", ROOT / "scripts/review_admission_v2_core.py")
assert CORE_SPEC and CORE_SPEC.loader
review_core = importlib.util.module_from_spec(CORE_SPEC)
CORE_SPEC.loader.exec_module(review_core)

ADAPTER_SPEC = importlib.util.spec_from_file_location("review_archive", ROOT / "scripts/review_admission_v2_archive.py")
assert ADAPTER_SPEC and ADAPTER_SPEC.loader
review_archive = importlib.util.module_from_spec(ADAPTER_SPEC)
ADAPTER_SPEC.loader.exec_module(review_archive)


class ArchiveAdapterTests(unittest.TestCase):
    def test_exact_prospective_identity_is_parsed(self) -> None:
        sha = "a" * 40
        body = f"head: {'b' * 40}\nprospective merge: {sha}\nprospective merge tree: {'c' * 40}\n"
        self.assertEqual(sha, review_archive.prospective_from_body(body))

    def test_missing_or_duplicate_prospective_identity_fails(self) -> None:
        with self.assertRaises(review_core.AdmissionError):
            review_archive.prospective_from_body("no identity")
        sha = "a" * 40
        with self.assertRaises(review_core.AdmissionError):
            review_archive.prospective_from_body(
                f"prospective merge: {sha}\nprospective merge: {sha}\n"
            )

    def test_synthetic_open_pull_preserves_reviewed_tuple(self) -> None:
        prospective = "a" * 40
        pull = {
            "state": "closed",
            "merged": True,
            "draft": False,
            "mergeable": None,
            "merge_commit_sha": "f" * 40,
            "body": "packet",
            "head": {"sha": "b" * 40},
            "base": {"sha": "c" * 40},
        }
        value = review_archive.synthetic_open_pull(pull, prospective)
        self.assertEqual("open", value["state"])
        self.assertTrue(value["mergeable"])
        self.assertEqual(prospective, value["merge_commit_sha"])
        self.assertEqual(pull["head"], value["head"])
        self.assertEqual("closed", pull["state"])

    def test_unmerged_pull_is_rejected(self) -> None:
        with self.assertRaises(review_core.AdmissionError):
            review_archive.synthetic_open_pull(
                {"state": "closed", "merged": False, "draft": False},
                "a" * 40,
            )


if __name__ == "__main__":
    unittest.main()
