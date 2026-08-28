from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "validate_dependency_bakeoff_v1",
    ROOT / "scripts" / "validate_dependency_bakeoff_v1.py",
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DependencyBakeoffValidationTests(unittest.TestCase):
    def test_seed_catalog_is_complete_but_unselected(self):
        candidate_count, capability_count = MODULE.validate()
        self.assertEqual(candidate_count, 25)
        self.assertEqual(capability_count, 16)

    def test_main_returns_success_for_the_checked_in_seed(self):
        self.assertEqual(MODULE.main(), 0)


if __name__ == "__main__":
    unittest.main()
