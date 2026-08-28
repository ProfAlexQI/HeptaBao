from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/h02_openraft_inmemory_cluster_evidence_v1.py"
SCHEMA = json.loads((ROOT / "schemas/heptabao_h02_openraft_cluster_evidence_v1.schema.json").read_text())

spec = importlib.util.spec_from_file_location("cluster_evidence", SCRIPT)
mod = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(mod)


def output(seed: str, fail_case: str | None = None) -> str:
    lines = [
        json.dumps(
            {
                "kind": "meta",
                "candidate_id": "HB-DEP-RAFT-OPENRAFT",
                "version": "0.10.0-alpha.33",
                "profile_id": "HB-H02-BEHAVIOR-RAFT-OPENRAFT-INMEMORY-0_10_0_ALPHA_33",
                "domain": "RAFT",
                "seed": seed,
                "execution_scope": "REAL_OPENRAFT_INMEMORY_CLUSTER_WITH_TEST_MEMSTORE",
                "durability_class": "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
                "qualification": False,
                "selection_effect": "NONE",
                "authority_effect": "NONE",
            }
        )
    ]
    for case_id in mod.CASES:
        detail = {"value": case_id}
        if case_id == "raft-committed-snapshot-conflict-rejected":
            detail["full_snapshot_rpc_seen"] = True
        lines.append(
            json.dumps(
                {
                    "kind": "case",
                    "case_id": case_id,
                    "status": "FAIL" if case_id == fail_case else "PASS",
                    "assertion_count": 2,
                    "detail": detail,
                }
            )
        )
    return "\n".join(lines) + "\n"


class EvidenceTests(unittest.TestCase):
    def collect(self, first: str, second: str | None = None, exit_code: int = 0):
        td = tempfile.TemporaryDirectory()
        root = Path(td.name)
        adapter = root / "adapter.jsonl"
        replay = root / "replay.jsonl"
        manifest = root / "Cargo.toml"
        lockfile = root / "Cargo.lock"
        adapter.write_text(first)
        replay.write_text(first if second is None else second)
        manifest.write_text("[package]\nname='x'\n")
        lockfile.write_text("version = 4\n")
        args = Namespace(
            adapter_output=str(adapter),
            replay_output=str(replay),
            execution_exit_code=exit_code,
            seed="0x5eed20260828cafe",
            toolchain="1.98.0",
            manifest=str(manifest),
            cargo_lock=str(lockfile),
            source_commit="1" * 40,
            source_tree="2" * 40,
            branch="test",
            clean_tree=True,
            environment_id="test-environment-0001",
            executor_kind="local-container",
            runner_id=None,
            runner_name="test",
        )
        return td, mod.collect(args)

    def assert_schema(self, value):
        errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
        self.assertEqual([], [error.message for error in errors])

    def test_complete_replay_is_pass_but_promotion_blocked(self):
        td, value = self.collect(output("0x5eed20260828cafe"))
        self.addCleanup(td.cleanup)
        self.assert_schema(value)
        self.assertEqual("EXECUTED_PASS", value["status"])
        self.assertEqual("BLOCK_PENDING_DURABLE_STORE_AND_HOSTILE_FAULTS", value["promotion_effect"])
        self.assertFalse(value["qualification"])
        self.assertEqual("NONE", value["authority_effect"])

    def test_replay_mismatch_blocks(self):
        first = output("0x5eed20260828cafe")
        second = output("0x5eed20260828cafe").replace('"assertion_count": 2', '"assertion_count": 3', 1)
        td, value = self.collect(first, second)
        self.addCleanup(td.cleanup)
        self.assertEqual("BLOCKED", value["status"])
        self.assertFalse(value["replay_match"])

    def test_nonzero_exit_blocks_and_preserves_evidence(self):
        td, value = self.collect(output("0x5eed20260828cafe"), exit_code=101)
        self.addCleanup(td.cleanup)
        self.assertEqual("BLOCKED", value["status"])
        self.assertEqual(6, len(value["cases"]))

    def test_failed_case_is_executed_fail(self):
        td, value = self.collect(output("0x5eed20260828cafe", mod.CASES[4]))
        self.addCleanup(td.cleanup)
        self.assertEqual("EXECUTED_FAIL", value["status"])
        self.assertEqual(1, value["summary"]["failed"])

    def test_missing_case_blocks(self):
        raw = output("0x5eed20260828cafe")
        raw = "\n".join(line for line in raw.splitlines() if mod.CASES[0] not in line) + "\n"
        td, value = self.collect(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual("BLOCKED", value["status"])
        self.assertEqual(1, value["summary"]["blocked"])

    def test_candidate_meta_mismatch_blocks(self):
        raw = output("0x5eed20260828cafe").replace("HB-DEP-RAFT-OPENRAFT", "WRONG", 1)
        td, value = self.collect(raw)
        self.addCleanup(td.cleanup)
        self.assertEqual("BLOCKED", value["status"])

    def test_false_pass_with_unknown_is_rejected_by_schema(self):
        td, value = self.collect(output("0x5eed20260828cafe"))
        self.addCleanup(td.cleanup)
        value["summary"]["unknown"] = 1
        errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
        self.assertTrue(errors)

    def test_false_authority_is_rejected_by_schema(self):
        td, value = self.collect(output("0x5eed20260828cafe"))
        self.addCleanup(td.cleanup)
        value["authority_effect"] = "PRODUCTION"
        errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
        self.assertTrue(errors)

    def test_snapshot_pass_requires_full_snapshot_rpc(self):
        td, value = self.collect(output("0x5eed20260828cafe"))
        self.addCleanup(td.cleanup)
        value["scope"]["real_full_snapshot_rpc"] = False
        errors = list(Draft202012Validator(SCHEMA).iter_errors(value))
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
