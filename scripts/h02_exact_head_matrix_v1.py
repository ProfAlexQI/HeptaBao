#!/usr/bin/env python3
"""Execute and semantically validate the complete H02 exact-head matrix.

The runner is deliberately read-only with respect to the repository. It runs
all required toolchain/seed/probe combinations, preserves stdout, stderr and
exit codes for every entry, writes a deterministic machine summary, and exits
successfully only when every application-level result passes.

It does not grant qualification, dependency selection, compatibility, or any
operational authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, NamedTuple

SCHEMA_ID = "heptabao.h02-exact-head-matrix-summary.v1"
CANDIDATE_ID = "HB-DEP-RAFT-OPENRAFT"
CANDIDATE_VERSION = "0.10.0-alpha.33"
TOOLCHAINS = ("1.88.0", "1.98.0")
SEEDS = (
    "0x5eed20260828cafe",
    "0x8badf00d12345678",
    "0xd15ea5e5cafef00d",
)
EXPECTED_INMEMORY_CASES = {
    "raft-deterministic-apply-and-restart",
    "raft-committed-snapshot-conflict-rejected",
    "raft-joint-membership-single-writer",
    "raft-process-pause-plus-partition",
    "raft-quorum-loss-fail-closed",
    "raft-incomplete-run-replay-diagnostics",
}
EXPECTED_DURABLE_CASES = {
    "durable-three-node-fsync-and-replication",
    "durable-full-cluster-restart-and-read-index",
    "durable-post-restart-write-survives-second-restart",
    "durable-snapshot-state-atomic-generation-reopen",
    "durable-log-corruption-fails-closed",
    "durable-state-corruption-fails-closed",
    "durable-isolated-writer-does-not-advance-commit",
}
HEX40 = re.compile(r"^[0-9a-f]{40}$")
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


class ValidationError(RuntimeError):
    """An application result did not satisfy its fail-closed contract."""


class Probe(NamedTuple):
    kind: str
    binary: str
    arguments: tuple[str, ...]
    validator: Callable[[str, str], str]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def evidence_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def require_authority_closed(value: dict[str, Any]) -> None:
    require(value.get("qualification") is False, "qualification must remain false")
    require(
        value.get("selection_effect") == "NONE",
        "selection_effect must remain NONE",
    )
    require(value.get("authority_effect") == "NONE", "authority_effect must remain NONE")


def parse_single_json(stdout: str) -> dict[str, Any]:
    try:
        value = json.loads(stdout)
    except json.JSONDecodeError as error:
        raise ValidationError(f"stdout is not one JSON object: {error}") from error
    require(isinstance(value, dict), "stdout JSON must be an object")
    return value


def parse_json_lines(stdout: str) -> list[dict[str, Any]]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    require(lines, "stdout JSONL is empty")
    values: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError as error:
            raise ValidationError(f"stdout JSONL line {index} is invalid: {error}") from error
        require(isinstance(value, dict), f"stdout JSONL line {index} is not an object")
        values.append(value)
    return values


def validate_identity(value: dict[str, Any], seed: str) -> None:
    require(value.get("candidate_id") == CANDIDATE_ID, "candidate_id drift")
    require(value.get("version") == CANDIDATE_VERSION, "candidate version drift")
    require(value.get("seed") == seed, "seed drift")
    require_authority_closed(value)


def validate_inmemory(stdout: str, seed: str) -> str:
    values = parse_json_lines(stdout)
    meta = [value for value in values if value.get("kind") == "meta"]
    cases = [value for value in values if value.get("kind") == "case"]
    errors = [value for value in values if value.get("kind") == "harness_error"]
    require(len(meta) == 1, "in-memory output must contain exactly one meta object")
    require(not errors, "in-memory output contains a harness_error")
    validate_identity(meta[0], seed)
    require(
        meta[0].get("durability_class") == "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
        "in-memory durability boundary drift",
    )
    require(len(cases) == 6, "in-memory output must contain exactly six cases")
    case_ids = {str(case.get("case_id")) for case in cases}
    require(case_ids == EXPECTED_INMEMORY_CASES, "in-memory case set drift")
    failed = [case.get("case_id") for case in cases if case.get("status") != "PASS"]
    require(not failed, f"in-memory cases did not pass: {failed!r}")
    return "EXECUTED_PASS"


def validate_hostile(stdout: str, seed: str) -> str:
    value = parse_single_json(stdout)
    require(
        value.get("schema") == "heptabao.h02-openraft-hostile-snapshot-result.v1",
        "hostile result schema drift",
    )
    validate_identity(value, seed)
    status = value.get("status")
    require(status == "EXECUTED_PASS", f"hostile application status is {status!r}")
    require(value.get("phase_reached") is True, "hostile injection phase was not reached")
    require(
        value.get("outcome") == "REJECTED_OR_ABORTED_AFTER_INJECTION",
        "hostile snapshot was not semantically rejected",
    )
    return str(status)


def validate_blocker(stdout: str, seed: str) -> str:
    value = parse_single_json(stdout)
    require(
        value.get("schema") == "heptabao.h02-blocker-closure-result.v1",
        "blocker result schema drift",
    )
    validate_identity(value, seed)
    status = value.get("status")
    require(status == "EXECUTED_PASS", f"blocker application status is {status!r}")
    components = value.get("components")
    require(isinstance(components, dict), "blocker components are missing")
    require(
        set(components) == {"os_suspend", "durable_faults", "clock_faults"},
        "blocker component set drift",
    )
    for name, component in components.items():
        require(isinstance(component, dict), f"blocker component {name} is not an object")
        require(
            component.get("status") == "EXECUTED_PASS",
            f"blocker component {name} did not pass",
        )
        require_authority_closed(component)
    return str(status)


def validate_durable(stdout: str, seed: str) -> str:
    value = parse_single_json(stdout)
    require(
        value.get("schema") == "heptabao.h02-openraft-durable-store-result.v1",
        "durable result schema drift",
    )
    validate_identity(value, seed)
    status = value.get("status")
    require(status == "EXECUTED_PASS", f"durable application status is {status!r}")
    cases = value.get("cases")
    require(isinstance(cases, list) and len(cases) == 7, "durable result must contain seven cases")
    case_ids = {str(case.get("case_id")) for case in cases if isinstance(case, dict)}
    require(case_ids == EXPECTED_DURABLE_CASES, "durable case set drift")
    failed = [
        case.get("case_id")
        for case in cases
        if not isinstance(case, dict) or case.get("status") != "PASS"
    ]
    require(not failed, f"durable cases did not pass: {failed!r}")
    scope = value.get("scope")
    require(isinstance(scope, dict), "durable scope is missing")
    for key in (
        "raft_log_storage_implemented",
        "raft_state_machine_implemented",
        "state_machine_persisted_before_responder",
        "snapshot_state_atomic_bundle_publish",
        "state_publish_after_durable_write",
        "full_cluster_disk_restart",
        "read_index_after_restart",
        "corruption_rejected",
    ):
        require(scope.get(key) is True, f"durable scope flag not proven: {key}")
    require(scope.get("real_openraft_nodes") == 3, "durable node count drift")
    require(scope.get("kernel_power_loss") is False, "logical lab must not claim kernel power loss")
    require(scope.get("production_selected") is False, "durable candidate must remain unselected")
    return str(status)


PROBES = (
    Probe(
        kind="inmemory",
        binary="heptabao-h02-openraft-inmemory-cluster",
        arguments=(),
        validator=validate_inmemory,
    ),
    Probe(
        kind="hostile",
        binary="heptabao-h02-openraft-fault-lab",
        arguments=("--mode", "hostile-snapshot-parent"),
        validator=validate_hostile,
    ),
    Probe(
        kind="blocker",
        binary="heptabao-h02-openraft-blocker-closure-lab",
        arguments=("--mode", "all"),
        validator=validate_blocker,
    ),
    Probe(
        kind="durable",
        binary="heptabao-h02-openraft-durable-store-lab",
        arguments=(),
        validator=validate_durable,
    ),
)


def entry_id(probe: Probe, toolchain: str, seed: str) -> str:
    return f"{probe.kind}-{toolchain}-{seed.removeprefix('0x')}"


def expected_entry_ids(
    toolchains: Iterable[str] = TOOLCHAINS,
    seeds: Iterable[str] = SEEDS,
    probes: Iterable[Probe] = PROBES,
) -> set[str]:
    return {
        entry_id(probe, toolchain, seed)
        for toolchain in toolchains
        for seed in seeds
        for probe in probes
    }


def validate_captured_result(
    probe: Probe,
    seed: str,
    stdout: str,
    exit_code: int | None,
    timed_out: bool = False,
    spawn_error: str | None = None,
) -> tuple[str, str | None, list[str]]:
    """Return conclusion, application status and validation errors.

    Process exit status is necessary but not sufficient. A semantic
    EXECUTED_FAIL in stdout is always a failure even if the process exits 0.
    """

    errors: list[str] = []
    application_status: str | None = None
    if spawn_error is not None:
        return "UNEXECUTED", None, [f"process could not be started: {spawn_error}"]
    if timed_out:
        errors.append("process exceeded the bounded entry timeout")
    try:
        application_status = probe.validator(stdout, seed)
    except ValidationError as error:
        errors.append(str(error))
    if exit_code is None:
        errors.append("process exit code is unavailable")
    elif exit_code != 0:
        errors.append(f"process exit code was {exit_code}")

    if not errors and application_status == "EXECUTED_PASS" and exit_code == 0:
        return "PASS", application_status, []

    if application_status == "BLOCKED":
        return "BLOCKED", application_status, errors
    return "FAIL", application_status, errors


def run_entry(
    *,
    probe: Probe,
    toolchain: str,
    seed: str,
    manifest: Path,
    output_dir: Path,
    target_root: Path,
    timeout_seconds: int,
) -> dict[str, Any]:
    identifier = entry_id(probe, toolchain, seed)
    stdout_path = output_dir / f"{identifier}.stdout"
    stderr_path = output_dir / f"{identifier}.stderr"
    exit_path = output_dir / f"{identifier}.exit"
    command = [
        "cargo",
        f"+{toolchain}",
        "run",
        "--quiet",
        "--locked",
        "--manifest-path",
        str(manifest),
        "--bin",
        probe.binary,
        "--",
        *probe.arguments,
        "--seed",
        seed,
    ]
    environment = os.environ.copy()
    environment["CARGO_TARGET_DIR"] = str(Path(f"{target_root}-{toolchain}"))
    started_at = utc_now()
    started_monotonic = time.monotonic()
    exit_code: int | None = None
    timed_out = False
    spawn_error: str | None = None
    stdout_bytes = b""
    stderr_bytes = b""
    try:
        completed = subprocess.run(
            command,
            cwd=manifest.parent,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=timeout_seconds,
        )
        exit_code = completed.returncode
        stdout_bytes = completed.stdout
        stderr_bytes = completed.stderr
    except subprocess.TimeoutExpired as error:
        timed_out = True
        stdout_bytes = error.stdout or b""
        stderr_bytes = error.stderr or b""
    except OSError as error:
        spawn_error = f"{type(error).__name__}: {error}"
        stderr_bytes = spawn_error.encode("utf-8", errors="replace")

    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    completed_at = utc_now()
    stdout_path.write_bytes(stdout_bytes)
    stderr_path.write_bytes(stderr_bytes)
    exit_path.write_text("UNAVAILABLE\n" if exit_code is None else f"{exit_code}\n", encoding="utf-8")

    stdout = stdout_bytes.decode("utf-8", errors="replace")
    conclusion, application_status, errors = validate_captured_result(
        probe,
        seed,
        stdout,
        exit_code,
        timed_out=timed_out,
        spawn_error=spawn_error,
    )
    return {
        "entry_id": identifier,
        "kind": probe.kind,
        "binary": probe.binary,
        "toolchain": toolchain,
        "seed": seed,
        "command": command,
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "exit_code": exit_code,
        "timed_out": timed_out,
        "conclusion": conclusion,
        "application_status": application_status,
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "exit_path": exit_path.name,
        "stdout_digest": sha256_bytes(stdout_bytes),
        "stderr_digest": sha256_bytes(stderr_bytes),
        "validation_errors": errors,
    }


def summarize_entries(entries: list[dict[str, Any]]) -> dict[str, int]:
    result = {"pass": 0, "fail": 0, "blocked": 0, "unknown": 0, "unexecuted": 0}
    for entry in entries:
        conclusion = entry.get("conclusion")
        if conclusion == "PASS":
            result["pass"] += 1
        elif conclusion == "FAIL":
            result["fail"] += 1
        elif conclusion == "BLOCKED":
            result["blocked"] += 1
        elif conclusion == "UNEXECUTED":
            result["unexecuted"] += 1
        else:
            result["unknown"] += 1
    return result


def build_summary(
    *,
    repository: str,
    ref: str,
    commit: str,
    tree: str,
    manifest: Path,
    lock: Path,
    entries: list[dict[str, Any]],
    started_at: str,
    completed_at: str,
) -> dict[str, Any]:
    required_ids = expected_entry_ids()
    actual_ids = {str(entry.get("entry_id")) for entry in entries}
    counts = summarize_entries(entries)
    missing_ids = sorted(required_ids - actual_ids)
    unexpected_ids = sorted(actual_ids - required_ids)
    if missing_ids:
        counts["unexecuted"] += len(missing_ids)
    if unexpected_ids:
        counts["unknown"] += len(unexpected_ids)
    result = (
        "PASS"
        if len(entries) == len(required_ids)
        and not missing_ids
        and not unexpected_ids
        and counts == {"pass": 24, "fail": 0, "blocked": 0, "unknown": 0, "unexecuted": 0}
        else "FAIL"
    )
    return {
        "schema": SCHEMA_ID,
        "source_binding": {
            "repository": repository,
            "ref": ref,
            "commit": commit,
            "tree": tree,
            "clean_tree": True,
        },
        "dependency_binding": {
            "manifest_path": evidence_path(manifest),
            "manifest_digest": sha256_file(manifest),
            "lock_path": evidence_path(lock),
            "lock_digest": sha256_file(lock),
        },
        "matrix": {
            "toolchains": list(TOOLCHAINS),
            "seeds": list(SEEDS),
            "kinds": [probe.kind for probe in PROBES],
            "required_entry_count": len(required_ids),
            "executed_entry_count": sum(
                1 for entry in entries if entry.get("exit_code") is not None or entry.get("timed_out")
            ),
            "missing_entry_ids": missing_ids,
            "unexpected_entry_ids": unexpected_ids,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "entries": entries,
        "counts": counts,
        "result": result,
        "qualification": False,
        "compatibility_claim": False,
        "selection_effect": "NONE",
        "authority_effect": "NONE",
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--ref", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tree", required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--cargo-target-root", type=Path, required=True)
    parser.add_argument("--entry-timeout-seconds", type=int, default=180)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.repository != "ProfHepta/HeptaBao":
        print("unexpected repository identity", file=sys.stderr)
        return 2
    if not HEX40.fullmatch(args.commit) or not HEX40.fullmatch(args.tree):
        print("commit and tree must be full lowercase 40-hex object IDs", file=sys.stderr)
        return 2
    if args.entry_timeout_seconds < 1:
        print("entry timeout must be positive", file=sys.stderr)
        return 2

    manifest = args.manifest.resolve()
    lock = manifest.with_name("Cargo.lock")
    if not manifest.is_file() or not lock.is_file():
        print("manifest or committed lock file is missing", file=sys.stderr)
        return 2
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    started_at = utc_now()
    entries: list[dict[str, Any]] = []
    for toolchain in TOOLCHAINS:
        for seed in SEEDS:
            for probe in PROBES:
                entry = run_entry(
                    probe=probe,
                    toolchain=toolchain,
                    seed=seed,
                    manifest=manifest,
                    output_dir=output_dir,
                    target_root=args.cargo_target_root.resolve(),
                    timeout_seconds=args.entry_timeout_seconds,
                )
                entries.append(entry)
                print(
                    f"{entry['entry_id']}: {entry['conclusion']} "
                    f"exit={entry['exit_code']} app={entry['application_status']}",
                    flush=True,
                )
    completed_at = utc_now()
    summary = build_summary(
        repository=args.repository,
        ref=args.ref,
        commit=args.commit,
        tree=args.tree,
        manifest=manifest,
        lock=lock,
        entries=entries,
        started_at=started_at,
        completed_at=completed_at,
    )
    summary_path = output_dir / "matrix-summary.json"
    summary_path.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "summary": str(summary_path),
                "result": summary["result"],
                "counts": summary["counts"],
                "qualification": False,
                "authority_effect": "NONE",
            },
            sort_keys=True,
        )
    )
    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
