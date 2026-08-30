#!/usr/bin/env python3
"""Execute and semantically validate the complete H02 exact-head matrix.

The runner is deliberately read-only with respect to the repository. It binds
itself to the actual Git checkout, runs every required toolchain/seed/probe
combination without fail-fast truncation, preserves process and application
results, terminates timed-out process groups, and emits a digest-bound summary.

It does not grant qualification, dependency selection, compatibility, or any
operational authority.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
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
EXPECTED_MANIFEST = REPOSITORY_ROOT / "probes/h02/openraft-tokio/Cargo.toml"
APPLICATION_STATUSES = {
    "EXECUTED_PASS",
    "EXECUTED_FAIL",
    "BLOCKED",
    "UNKNOWN",
    "UNEXECUTED",
}


class ValidationError(RuntimeError):
    """A source binding or application result violated its contract."""


class Probe(NamedTuple):
    kind: str
    binary: str
    arguments: tuple[str, ...]
    validator: Callable[[str, str], str]
    status_extractor: Callable[[str], str | None]


class ProcessCapture(NamedTuple):
    process_started: bool
    exit_code: int | None
    timed_out: bool
    spawn_error: str | None
    stdout: bytes
    stderr: bytes


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace(
        "+00:00", "Z"
    )


def sha256_bytes(value: bytes) -> str:
    return "sha256:" + hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def canonical_json_digest(value: Any) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return sha256_bytes(encoded)


def evidence_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(REPOSITORY_ROOT).as_posix()
    except ValueError:
        return resolved.as_posix()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def path_is_within(path: Path, parent: Path) -> bool:
    try:
        path.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


def git_text(*arguments: str) -> str:
    completed = subprocess.run(
        ["git", *arguments],
        cwd=REPOSITORY_ROOT,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        raise ValidationError(
            f"git {' '.join(arguments)} failed: {completed.stderr.strip()}"
        )
    return completed.stdout.strip()


def verify_source_binding(
    *,
    repository: str,
    commit: str,
    tree: str,
    manifest: Path,
    output_dir: Path,
    target_root: Path,
) -> None:
    """Bind caller-supplied metadata to the actual immutable checkout."""

    require(repository == "ProfHepta/HeptaBao", "unexpected repository identity")
    require(HEX40.fullmatch(commit) is not None, "commit must be full lowercase 40-hex")
    require(HEX40.fullmatch(tree) is not None, "tree must be full lowercase 40-hex")

    actual_root = Path(git_text("rev-parse", "--show-toplevel")).resolve()
    require(actual_root == REPOSITORY_ROOT.resolve(), "script is not running from its Git root")
    require(git_text("rev-parse", "HEAD") == commit, "declared commit does not match HEAD")
    require(
        git_text("rev-parse", "HEAD^{tree}") == tree,
        "declared tree does not match HEAD tree",
    )
    require(
        git_text("status", "--porcelain=v1", "--untracked-files=all") == "",
        "repository checkout is not clean",
    )

    resolved_manifest = manifest.resolve()
    require(
        resolved_manifest == EXPECTED_MANIFEST.resolve(),
        "manifest path is not the canonical OpenRaft probe manifest",
    )
    require(resolved_manifest.is_file(), "canonical manifest is missing")
    require(resolved_manifest.with_name("Cargo.lock").is_file(), "committed lock is missing")

    require(
        not path_is_within(output_dir, REPOSITORY_ROOT),
        "output directory must be outside the repository",
    )
    require(
        not path_is_within(target_root, REPOSITORY_ROOT),
        "Cargo target root must be outside the repository",
    )


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


def normalize_application_status(raw: Any) -> str | None:
    if raw == "PASS":
        return "EXECUTED_PASS"
    if raw == "FAIL":
        return "EXECUTED_FAIL"
    if isinstance(raw, str) and raw in APPLICATION_STATUSES:
        return raw
    return None


def combine_case_statuses(statuses: Iterable[Any]) -> str | None:
    normalized = [normalize_application_status(status) for status in statuses]
    if not normalized or any(status is None for status in normalized):
        return None
    values = set(normalized)
    for status in ("EXECUTED_FAIL", "BLOCKED", "UNKNOWN", "UNEXECUTED"):
        if status in values:
            return status
    return "EXECUTED_PASS" if values == {"EXECUTED_PASS"} else None


def extract_single_status(stdout: str) -> str | None:
    return normalize_application_status(parse_single_json(stdout).get("status"))


def extract_inmemory_status(stdout: str) -> str | None:
    values = parse_json_lines(stdout)
    if any(value.get("kind") == "harness_error" for value in values):
        return "BLOCKED"
    cases = [value for value in values if value.get("kind") == "case"]
    return combine_case_statuses(case.get("status") for case in cases)


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
    status = normalize_application_status(value.get("status"))
    require(status == "EXECUTED_PASS", f"hostile application status is {status!r}")
    require(value.get("phase_reached") is True, "hostile injection phase was not reached")
    require(
        value.get("outcome") == "REJECTED_OR_ABORTED_AFTER_INJECTION",
        "hostile snapshot was not semantically rejected",
    )
    return status


def validate_blocker(stdout: str, seed: str) -> str:
    value = parse_single_json(stdout)
    require(
        value.get("schema") == "heptabao.h02-blocker-closure-result.v1",
        "blocker result schema drift",
    )
    validate_identity(value, seed)
    status = normalize_application_status(value.get("status"))
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
            normalize_application_status(component.get("status")) == "EXECUTED_PASS",
            f"blocker component {name} did not pass",
        )
        require_authority_closed(component)
    return status


def validate_durable(stdout: str, seed: str) -> str:
    value = parse_single_json(stdout)
    require(
        value.get("schema") == "heptabao.h02-openraft-durable-store-result.v1",
        "durable result schema drift",
    )
    validate_identity(value, seed)
    status = normalize_application_status(value.get("status"))
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
    return status


PROBES = (
    Probe(
        kind="inmemory",
        binary="heptabao-h02-openraft-inmemory-cluster",
        arguments=(),
        validator=validate_inmemory,
        status_extractor=extract_inmemory_status,
    ),
    Probe(
        kind="hostile",
        binary="heptabao-h02-openraft-fault-lab",
        arguments=("--mode", "hostile-snapshot-parent"),
        validator=validate_hostile,
        status_extractor=extract_single_status,
    ),
    Probe(
        kind="blocker",
        binary="heptabao-h02-openraft-blocker-closure-lab",
        arguments=("--mode", "all"),
        validator=validate_blocker,
        status_extractor=extract_single_status,
    ),
    Probe(
        kind="durable",
        binary="heptabao-h02-openraft-durable-store-lab",
        arguments=(),
        validator=validate_durable,
        status_extractor=extract_single_status,
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
    *,
    process_started: bool = True,
    timed_out: bool = False,
    spawn_error: str | None = None,
) -> tuple[str, str | None, list[str]]:
    """Return conclusion, application status and validation errors.

    Process exit status is necessary but not sufficient. Explicit BLOCKED,
    UNKNOWN and UNEXECUTED application states remain distinct instead of being
    collapsed into a generic process failure.
    """

    if spawn_error is not None or not process_started:
        detail = spawn_error or "process was not started"
        return "UNEXECUTED", None, [f"process could not be started: {detail}"]

    errors: list[str] = []
    application_status: str | None = None
    try:
        application_status = probe.status_extractor(stdout)
    except ValidationError as error:
        errors.append(f"application status extraction failed: {error}")

    try:
        validated_status = probe.validator(stdout, seed)
        if application_status is None:
            application_status = validated_status
        elif validated_status != application_status:
            errors.append(
                f"application status disagreement: extracted={application_status} "
                f"validated={validated_status}"
            )
    except ValidationError as error:
        errors.append(str(error))

    if timed_out:
        errors.append("process exceeded the bounded entry timeout")
    if exit_code is None:
        errors.append("process exit code is unavailable")
    elif exit_code != 0:
        errors.append(f"process exit code was {exit_code}")

    if not errors and application_status == "EXECUTED_PASS" and exit_code == 0:
        return "PASS", application_status, []
    if timed_out or application_status == "BLOCKED":
        return "BLOCKED", application_status, errors
    if application_status == "UNEXECUTED":
        return "UNEXECUTED", application_status, errors
    if application_status == "UNKNOWN":
        return "UNKNOWN", application_status, errors
    return "FAIL", application_status, errors


def terminate_process_group(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(process.pid, signal.SIGKILL)
        else:
            process.kill()
    except (ProcessLookupError, PermissionError, OSError):
        process.kill()


def capture_process(
    command: list[str],
    *,
    cwd: Path,
    environment: dict[str, str],
    timeout_seconds: int,
) -> ProcessCapture:
    process: subprocess.Popen[bytes] | None = None
    try:
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=environment,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=(os.name == "posix"),
        )
    except OSError as error:
        detail = f"{type(error).__name__}: {error}"
        return ProcessCapture(False, None, False, detail, b"", detail.encode("utf-8"))

    try:
        stdout, stderr = process.communicate(timeout=timeout_seconds)
        return ProcessCapture(True, process.returncode, False, None, stdout, stderr)
    except subprocess.TimeoutExpired:
        terminate_process_group(process)
        stdout, stderr = process.communicate()
        return ProcessCapture(True, process.returncode, True, None, stdout, stderr)


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
    environment["CARGO_TERM_COLOR"] = "never"
    environment["RUST_BACKTRACE"] = "1"

    started_at = utc_now()
    started_monotonic = time.monotonic()
    captured = capture_process(
        command,
        cwd=REPOSITORY_ROOT,
        environment=environment,
        timeout_seconds=timeout_seconds,
    )
    duration_ms = int((time.monotonic() - started_monotonic) * 1000)
    completed_at = utc_now()

    stdout_path.write_bytes(captured.stdout)
    stderr_path.write_bytes(captured.stderr)
    exit_path.write_text(
        "UNAVAILABLE\n" if captured.exit_code is None else f"{captured.exit_code}\n",
        encoding="utf-8",
    )

    stdout = captured.stdout.decode("utf-8", errors="replace")
    conclusion, application_status, errors = validate_captured_result(
        probe,
        seed,
        stdout,
        captured.exit_code,
        process_started=captured.process_started,
        timed_out=captured.timed_out,
        spawn_error=captured.spawn_error,
    )
    return {
        "entry_id": identifier,
        "kind": probe.kind,
        "binary": probe.binary,
        "toolchain": toolchain,
        "seed": seed,
        "command": command,
        "command_digest": canonical_json_digest(command),
        "started_at": started_at,
        "completed_at": completed_at,
        "duration_ms": duration_ms,
        "process_started": captured.process_started,
        "exit_code": captured.exit_code,
        "timed_out": captured.timed_out,
        "conclusion": conclusion,
        "application_status": application_status,
        "stdout_path": stdout_path.name,
        "stderr_path": stderr_path.name,
        "exit_path": exit_path.name,
        "stdout_digest": sha256_bytes(captured.stdout),
        "stderr_digest": sha256_bytes(captured.stderr),
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
    runner_errors: list[str] | None = None,
) -> dict[str, Any]:
    required_ids = expected_entry_ids()
    entry_ids = [str(entry.get("entry_id")) for entry in entries]
    actual_ids = set(entry_ids)
    counts = summarize_entries(entries)
    missing_ids = sorted(required_ids - actual_ids)
    unexpected_ids = sorted(actual_ids - required_ids)
    duplicate_ids = sorted({identifier for identifier in entry_ids if entry_ids.count(identifier) > 1})
    errors = list(runner_errors or [])
    result = (
        "PASS"
        if len(entries) == len(required_ids)
        and not missing_ids
        and not unexpected_ids
        and not duplicate_ids
        and not errors
        and counts
        == {"pass": 24, "fail": 0, "blocked": 0, "unknown": 0, "unexecuted": 0}
        else "FAIL"
    )
    return {
        "schema": SCHEMA_ID,
        "source_binding": {
            "repository": repository,
            "ref": ref,
            "commit": commit,
            "tree": tree,
            "clean_tree": not errors,
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
                1 for entry in entries if entry.get("process_started") is True
            ),
            "missing_entry_ids": missing_ids,
            "unexpected_entry_ids": unexpected_ids,
            "duplicate_entry_ids": duplicate_ids,
        },
        "started_at": started_at,
        "completed_at": completed_at,
        "entries": entries,
        "counts": counts,
        "runner_errors": errors,
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


def current_source_errors(commit: str, tree: str) -> list[str]:
    errors: list[str] = []
    try:
        if git_text("rev-parse", "HEAD") != commit:
            errors.append("HEAD changed during matrix execution")
        if git_text("rev-parse", "HEAD^{tree}") != tree:
            errors.append("HEAD tree changed during matrix execution")
        if git_text("status", "--porcelain=v1", "--untracked-files=all") != "":
            errors.append("repository became dirty during matrix execution")
    except ValidationError as error:
        errors.append(str(error))
    return errors


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.ref.strip():
        print("ref must be non-empty", file=sys.stderr)
        return 2
    if not 1 <= args.entry_timeout_seconds <= 900:
        print("entry timeout must be between 1 and 900 seconds", file=sys.stderr)
        return 2

    manifest = args.manifest.resolve()
    output_dir = args.output_dir.resolve()
    target_root = args.cargo_target_root.resolve()
    try:
        verify_source_binding(
            repository=args.repository,
            commit=args.commit,
            tree=args.tree,
            manifest=manifest,
            output_dir=output_dir,
            target_root=target_root,
        )
    except ValidationError as error:
        print(f"source binding failed: {error}", file=sys.stderr)
        return 2

    lock = manifest.with_name("Cargo.lock")
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
                    target_root=target_root,
                    timeout_seconds=args.entry_timeout_seconds,
                )
                entries.append(entry)
                print(
                    f"{entry['entry_id']}: {entry['conclusion']} "
                    f"exit={entry['exit_code']} app={entry['application_status']}",
                    flush=True,
                )

    completed_at = utc_now()
    runner_errors = current_source_errors(args.commit, args.tree)
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
        runner_errors=runner_errors,
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
                "runner_errors": summary["runner_errors"],
                "qualification": False,
                "authority_effect": "NONE",
            },
            sort_keys=True,
        )
    )
    return 0 if summary["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
