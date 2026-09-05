from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("repaired_renderer", ROOT / "scripts/render_plan_v1_4_7.py")
assert SPEC and SPEC.loader
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class WorkflowRenderTests(unittest.TestCase):
    def test_frozen_generator_bytes_are_pinned(self) -> None:
        self.assertEqual(RENDERER.BASELINE_SHA256,
                         hashlib.sha256(RENDERER.BASELINE_PATH.read_bytes()).hexdigest())

    def test_complete_workflow_is_reproducible(self) -> None:
        path = ROOT / ".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml"
        self.assertEqual(path.read_bytes(), RENDERER.workflow_source().encode())

    def test_printf_escape_sequences_stay_inside_yaml_run_block(self) -> None:
        text = RENDERER.workflow_source()
        self.assertIn(r"printf 'source_kind=%s\nsource_sha=%s\ntree=%s\n'", text)
        self.assertNotIn("\nsource_sha=%s\n", text)

    def test_all_generated_shell_steps_parse(self) -> None:
        data = yaml.load(RENDERER.workflow_source(), Loader=yaml.BaseLoader)
        for step in data["jobs"]["validate"]["steps"]:
            if "run" in step:
                with self.subTest(name=step["name"]):
                    result = subprocess.run(["bash", "-n"], input=step["run"], text=True,
                                            capture_output=True, check=False)
                    self.assertEqual(0, result.returncode, result.stderr)

    def test_workflow_keeps_both_source_identities_and_read_only_permission(self) -> None:
        data = yaml.load(RENDERER.workflow_source(), Loader=yaml.BaseLoader)
        self.assertEqual({"pull_request"}, set(data["on"]))
        self.assertEqual({"contents": "read"}, data["permissions"])
        job = data["jobs"]["validate"]
        self.assertEqual(["exact-head", "prospective-merge"], job["strategy"]["matrix"]["source_kind"])
        self.assertNotIn("if", job)
        self.assertNotIn("continue-on-error", job)
        for step in job["steps"]:
            self.assertNotIn("continue-on-error", step)
        self.assertIn("cargo +1.98.0 test --locked --workspace --all-targets", RENDERER.workflow_source())
        self.assertIn("cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings",
                      RENDERER.workflow_source())

    def test_new_generator_and_regression_are_normatively_bound(self) -> None:
        paths = RENDERER.normative_paths(RENDERER.build_truth(ROOT))
        self.assertIn(Path("scripts/_render_plan_v1_4_7_baseline.py"), paths)
        self.assertIn(Path("scripts/render_plan_v1_4_7.py"), paths)
        self.assertIn(Path("tests/plan/test_workflow_render_v1_4_7.py"), paths)

    def test_check_mode_rejects_changes_without_repairing_them(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            path = root / "workflow.yml"
            path.write_text(RENDERER.workflow_source().replace("contents: read", "contents: write"))
            before = path.read_bytes()
            with self.assertRaises(SystemExit):
                RENDERER.write_or_compare(root, {Path("workflow.yml"): RENDERER.workflow_source()}, write=False)
            self.assertEqual(before, path.read_bytes())

    def test_missing_or_ambiguous_patch_anchor_fails_closed(self) -> None:
        for value in ("invalid", RENDERER._ORIGINAL_WORKFLOW() * 2):
            with self.subTest(value_length=len(value)), patch.object(RENDERER, "_ORIGINAL_WORKFLOW", return_value=value):
                with self.assertRaises(ValueError):
                    RENDERER.workflow_source()


if __name__ == "__main__":
    unittest.main()
