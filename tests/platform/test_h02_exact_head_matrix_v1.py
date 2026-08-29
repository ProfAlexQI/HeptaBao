from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[2]


def load_module():
    spec = importlib.util.spec_from_file_location(
        "h02_exact_head_matrix_v1",
        ROOT / "scripts/h02_exact_head_matrix_v1.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


runner = load_module()
SEED = runner.SEEDS[0]


def closed_authority() -> dict:
    return {
        "qualification": False,
        "selection_effect": "NONE",
        "authority_effect": "NONE",
    }


def inmemory_stdout() -> str:
    values = [
        {
            "kind": "meta",
            "candidate_id": runner.CANDIDATE_ID,
            "version": runner.CANDIDATE_VERSION,
            "seed": SEED,
            "durability_class": "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
            **closed_authority(),
        }
    ]
    values.extend(
        {
            "kind": "case",
            "case_id": case_id,
            "status": "PASS",
        }
        for case_id in sorted(runner.EXPECTED_INMEMORY_CASES)
    )
    return "\n".join(json.dumps(value) for value in values) + "\n"


def hostile_stdout(status: str = "EXECUTED_PASS") -> str:
    return json.dumps(
        {
            "schema": "heptabao.h02-openraft-hostile-snapshot-result.v1",
            "candidate_id": runner.CANDIDATE_ID,
            "version": runner.CANDIDATE_VERSION,
            "seed": SEED,
            "status": status,
            "phase_reached": True,
            "outcome": (
                "REJECTED_OR_ABORTED_AFTER_INJECTION"
                if status == "EXECUTED_PASS"
                else "ACCEPTED"
            ),
            **closed_authority(),
        }
    )


def blocker_stdout() -> str:
    component = {"status": "EXECUTED_PASS", **closed_authority()}
    return json.dumps(
        {
            "schema": "heptabao.h02-blocker-closure-result.v1",
            "candidate_id": runner.CANDIDATE_ID,
            "version": runner.CANDIDATE_VERSION,
            "seed": SEED,
            "status": "EXECUTED_PASS",
            "components": {
                "os_suspend": component,
                "durable_faults": component,
                "clock_faults": component,
            },
            **closed_authority(),
        }
    )


def durable_stdout() -> str:
    return json.dumps(
        {
            "schema": "heptabao.h02-openraft-durable-store-result.v1",
            "candidate_id": runner.CANDIDATE_ID,
            "version": runner.CANDIDATE_VERSION,
            "seed": SEED,
            "status": "EXECUTED_PASS",
            "cases": [
                {"case_id": case_id, "status": "PASS"}
                for case_id in sorted(runner.EXPECTED_DURABLE_CASES)
            ],
            "scope": {
                "real_openraft_nodes": 3,
                "raft_log_storage_implemented": True,
                "raft_state_machine_implemented": True,
                "state_machine_persisted_before_responder": True,
                "snapshot_state_atomic_bundle_publish": True,
                "state_publish_after_durable_write": True,
                "full_cluster_disk_restart": True,
                "read_index_after_restart": True,
                "corruption_rejected": True,
                "kernel_power_loss": False,
                "production_selected": False,
            },
            **closed_authority(),
        }
    )


class ExactHeadMatrixTests(unittest.TestCase):
    def test_all_application_contracts_accept_valid_results(self):
        self.assertEqual(runner.validate_inmemory(inmemory_stdout(), SEED), "EXECUTED_PASS")
        self.assertEqual(runner.validate_hostile(hostile_stdout(), SEED), "EXECUTED_PASS")
        self.assertEqual(runner.validate_blocker(blocker_stdout(), SEED), "EXECUTED_PASS")
        self.assertEqual(runner.validate_durable(durable_stdout(), SEED), "EXECUTED_PASS")

    def test_hostile_application_failure_is_failure_even_with_exit_zero(self):
        probe = next(item for item in runner.PROBES if item.kind == "hostile")
        conclusion, application_status, errors = runner.validate_captured_result(
            probe,
            SEED,
            hostile_stdout("EXECUTED_FAIL"),
            0,
        )
        self.assertEqual(conclusion, "FAIL")
        self.assertIsNone(application_status)
        self.assertTrue(any("EXECUTED_FAIL" in error for error in errors))

    def test_nonzero_exit_cannot_be_hidden_by_pass_json(self):
        probe = next(item for item in runner.PROBES if item.kind == "durable")
        conclusion, application_status, errors = runner.validate_captured_result(
            probe,
            SEED,
            durable_stdout(),
            9,
        )
        self.assertEqual(conclusion, "FAIL")
        self.assertEqual(application_status, "EXECUTED_PASS")
        self.assertIn("process exit code was 9", errors)

    def test_invalid_jsonl_line_is_rejected(self):
        with self.assertRaises(runner.ValidationError):
            runner.validate_inmemory(inmemory_stdout() + "not-json\n", SEED)

    def test_summary_requires_every_exact_entry(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "Cargo.toml"
            lock = root / "Cargo.lock"
            manifest.write_text("[package]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
            lock.write_text("version = 4\n", encoding="utf-8")
            summary = runner.build_summary(
                repository="ProfHepta/HeptaBao",
                ref="codex/test",
                commit="1" * 40,
                tree="2" * 40,
                manifest=manifest,
                lock=lock,
                entries=[],
                started_at="2026-08-30T00:00:00Z",
                completed_at="2026-08-30T00:01:00Z",
            )
        self.assertEqual(summary["result"], "FAIL")
        self.assertEqual(summary["matrix"]["required_entry_count"], 24)
        self.assertEqual(len(summary["matrix"]["missing_entry_ids"]), 24)
        self.assertEqual(summary["counts"]["unexecuted"], 24)
        self.assertFalse(summary["qualification"])
        self.assertEqual(summary["authority_effect"], "NONE")

    def test_complete_pass_summary_matches_schema(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = root / "Cargo.toml"
            lock = root / "Cargo.lock"
            manifest.write_text("[package]\nname='x'\nversion='0.0.0'\n", encoding="utf-8")
            lock.write_text("version = 4\n", encoding="utf-8")
            entries = []
            for toolchain in runner.TOOLCHAINS:
                for seed in runner.SEEDS:
                    for probe in runner.PROBES:
                        identifier = runner.entry_id(probe, toolchain, seed)
                        entries.append(
                            {
                                "entry_id": identifier,
                                "kind": probe.kind,
                                "binary": probe.binary,
                                "toolchain": toolchain,
                                "seed": seed,
                                "command": [
                                    "cargo",
                                    f"+{toolchain}",
                                    "run",
                                    "--bin",
                                    probe.binary,
                                    "--",
                                    "--seed",
                                    seed,
                                ],
                                "started_at": "2026-08-30T00:00:00Z",
                                "completed_at": "2026-08-30T00:00:01Z",
                                "duration_ms": 1000,
                                "exit_code": 0,
                                "timed_out": False,
                                "conclusion": "PASS",
                                "application_status": "EXECUTED_PASS",
                                "stdout_path": f"{identifier}.stdout",
                                "stderr_path": f"{identifier}.stderr",
                                "exit_path": f"{identifier}.exit",
                                "stdout_digest": runner.sha256_bytes(b"ok"),
                                "stderr_digest": runner.sha256_bytes(b""),
                                "validation_errors": [],
                            }
                        )
            summary = runner.build_summary(
                repository="ProfHepta/HeptaBao",
                ref="codex/test",
                commit="1" * 40,
                tree="2" * 40,
                manifest=manifest,
                lock=lock,
                entries=entries,
                started_at="2026-08-30T00:00:00Z",
                completed_at="2026-08-30T00:01:00Z",
            )
        schema = json.loads(
            (ROOT / "schemas/heptabao_h02_exact_head_matrix_summary_v1.schema.json").read_text(
                encoding="utf-8"
            )
        )
        errors = list(Draft202012Validator(schema).iter_errors(summary))
        self.assertEqual(errors, [])
        self.assertEqual(summary["result"], "PASS")
        self.assertEqual(summary["counts"]["pass"], 24)

    def test_expected_entry_ids_are_unique_and_complete(self):
        identifiers = runner.expected_entry_ids()
        self.assertEqual(len(identifiers), 24)
        self.assertEqual(
            identifiers,
            {
                runner.entry_id(probe, toolchain, seed)
                for toolchain in runner.TOOLCHAINS
                for seed in runner.SEEDS
                for probe in runner.PROBES
            },
        )


if __name__ == "__main__":
    unittest.main()
