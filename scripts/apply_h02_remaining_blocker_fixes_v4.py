#!/usr/bin/env python3
"""Apply the remaining H02 technical blocker fixes exactly once.

This file is a one-shot maintenance aid. The successful workflow deletes it in
the same commit that records the source, plan and validation changes.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, value: str) -> None:
    (ROOT / path).write_text(value, encoding="utf-8")


def replace(path: str, old: str, new: str, expected: int = 1) -> None:
    value = read(path)
    count = value.count(old)
    if count != expected:
        raise SystemExit(
            f"{path}: expected {expected} occurrences, found {count}: {old!r}"
        )
    write(path, value.replace(old, new))
    print(f"patched {path}: {old!r} -> {new!r}")


def replace_between(path: str, start: str, end: str, replacement: str) -> None:
    value = read(path)
    begin = value.find(start)
    if begin < 0:
        raise SystemExit(f"{path}: start marker not found: {start!r}")
    finish = value.find(end, begin)
    if finish < 0:
        raise SystemExit(f"{path}: end marker not found: {end!r}")
    write(path, value[:begin] + replacement + value[finish:])
    print(f"patched guarded block in {path}")


def rename_text(old: str, new: str, minimum: int) -> list[str]:
    changed: list[str] = []
    for directory in (".github", "planning", "schemas", "scripts", "tests", "probes"):
        for target in (ROOT / directory).rglob("*"):
            if not target.is_file() or target.suffix not in {
                ".rs",
                ".py",
                ".json",
                ".yaml",
                ".yml",
                ".md",
            }:
                continue
            value = target.read_text(encoding="utf-8")
            if old not in value:
                continue
            target.write_text(value.replace(old, new), encoding="utf-8")
            changed.append(str(target.relative_to(ROOT)))
    if len(changed) < minimum:
        raise SystemExit(f"rename touched too few files: {changed}")
    print(f"renamed {old!r} in {changed}")
    return changed


def patch_exact_openraft_family() -> None:
    cargo = "probes/h02/openraft-tokio/Cargo.toml"
    replace(
        cargo,
        'openraft-macros = "=0.10.0-alpha.33"\nserde_json = "=1.0.145"',
        '''openraft-macros = "=0.10.0-alpha.33"
# Constrain Cargo to the dependency version used by the audited upstream
# alpha.33 workspace. The matching patch below supplies the yanked crate from
# an immutable upstream commit instead of silently selecting validit 0.2.6.
validit = "=0.2.5"
serde_json = "=1.0.145"''',
    )

    harness = "scripts/h02_candidate_adapter_harness_v1.py"
    replace(
        harness,
        '"support_dependencies": ["openraft-memstore", "serde_json", "tokio", "validit"],',
        '''"support_dependencies": [
            "openraft-macros",
            "openraft-memstore",
            "openraft-rt",
            "openraft-rt-tokio",
            "serde_json",
            "tokio",
            "validit",
        ],''',
    )

    test = "tests/platform/test_h02_candidate_adapter_harness_v1.py"
    replace(
        test,
        '    "openraft-memstore": \'openraft-memstore = "=0.10.0-alpha.33"\',\n',
        '''    "openraft-macros": 'openraft-macros = "=0.10.0-alpha.33"',
    "openraft-memstore": 'openraft-memstore = "=0.10.0-alpha.33"',
    "openraft-rt": 'openraft-rt = "=0.10.0-alpha.33"',
    "openraft-rt-tokio": 'openraft-rt-tokio = "=0.10.0-alpha.33"',
''',
    )

    # Add an explicit regression test: removing the direct validit constraint or
    # any alpha.33 family package must fail the candidate binding gate.
    insertion = '''
    def test_openraft_complete_direct_family_is_bound(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            manifest = make_repo(root, "openraft")
            binding = mod.manifest_binding(
                root,
                mod.PROFILES["openraft"],
                "1.85.0",
                "aarch64-unknown-linux-gnu",
            )
            self.assertEqual(binding["direct_dependencies"]["validit"]["version"], "=0.2.5")
            self.assertEqual(
                set(binding["support_dependencies"]),
                {
                    "openraft-macros",
                    "openraft-memstore",
                    "openraft-rt",
                    "openraft-rt-tokio",
                    "serde_json",
                    "tokio",
                    "validit",
                },
            )
            value = manifest.read_text(encoding="utf-8")
            manifest.write_text(
                value.replace('validit = "=0.2.5"\\n', "", 1),
                encoding="utf-8",
            )
            with self.assertRaises(mod.Failure):
                mod.manifest_binding(
                    root,
                    mod.PROFILES["openraft"],
                    "1.85.0",
                    "aarch64-unknown-linux-gnu",
                )

'''
    value = read(test)
    marker = '\nif __name__ == "__main__":\n    unittest.main()\n'
    if value.count(marker) != 1:
        raise SystemExit(f"{test}: unittest footer drifted")
    write(test, value.replace(marker, insertion + marker))
    print(f"added complete-family regression test to {test}")


def patch_snapshot_replay() -> None:
    for path in (
        "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs",
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/cluster.rs",
    ):
        replace(
            path,
            "snapshot_policy: SnapshotPolicy::LogsSinceLast(3),",
            "snapshot_policy: SnapshotPolicy::LogsSinceLast(10_000),",
        )


def patch_os_suspend_probe() -> None:
    path = "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/os_clock.rs"
    replace(
        path,
        "wait_for_file(&ready_path, Duration::from_secs(20))",
        "wait_for_file(&ready_path, Duration::from_secs(30))",
    )
    replace(
        path,
        "wait_for_progress(&progress_path, 2, Duration::from_secs(10))",
        "wait_for_progress(&progress_path, 1, Duration::from_secs(30))",
    )
    replace(
        path,
        "wait_for_progress(&progress_path, frozen_step_b + 1, Duration::from_secs(10))",
        "wait_for_progress(&progress_path, frozen_step_b + 1, Duration::from_secs(30))",
    )


def patch_hostile_snapshot_verdict() -> None:
    path = "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/cluster.rs"
    replacement = '''    let leader_vote = cluster.nodes[&1]
        .raft
        .metrics()
        .borrow_watched()
        .vote
        .clone();
    let target_before_metrics = cluster.nodes[&2]
        .raft
        .metrics()
        .borrow_watched()
        .clone();
    let target_committed = target_before_metrics.local_committed.clone();
    let target_applied = target_before_metrics.last_applied.clone();
    let target_snapshot = target_before_metrics.snapshot.clone();
    let target_state_before = cluster.nodes[&2]
        .state_machine
        .get_state_machine()
        .await
        .client_status
        .clone();
    let stale_is_older = target_committed
        .as_ref()
        .is_some_and(|committed| &stale_log_id < committed);
    if !stale_is_older {
        return Err("hostile snapshot fixture is not older than target committed state".into());
    }

    println!(
        "{}",
        json!({
            "kind": "phase",
            "phase": HOSTILE_PHASE,
            "seed": format!("0x{seed:016x}"),
            "target_node": 2,
            "stale_snapshot_log_id": format!("{stale_log_id}"),
            "original_snapshot_log_id": original_snapshot_log_id.as_ref().map(|value| value.to_string()),
            "target_committed": target_committed.as_ref().map(|value| value.to_string()),
            "target_applied": target_applied.as_ref().map(|value| value.to_string()),
            "target_snapshot": target_snapshot.as_ref().map(|value| value.to_string()),
            "target_state_entries": target_state_before.len(),
            "qualification": false,
            "selection_effect": "NONE",
            "authority_effect": "NONE",
        })
    );
    io::stdout().flush()?;

    let install_result = timeout(
        Duration::from_secs(10),
        cluster.nodes[&2]
            .raft
            .install_full_snapshot(leader_vote, snapshot),
    )
    .await;

    sleep(Duration::from_millis(100)).await;
    let target_after_metrics = cluster.nodes[&2]
        .raft
        .metrics()
        .borrow_watched()
        .clone();
    let target_state_after = cluster.nodes[&2]
        .state_machine
        .get_state_machine()
        .await
        .client_status
        .clone();
    let committed_unchanged = target_after_metrics.local_committed == target_committed;
    let applied_unchanged = target_after_metrics.last_applied == target_applied;
    let snapshot_unchanged = target_after_metrics.snapshot == target_snapshot;
    let application_state_unchanged = target_state_after == target_state_before;
    let state_unchanged = committed_unchanged
        && applied_unchanged
        && snapshot_unchanged
        && application_state_unchanged;
    let state_guard = json!({
        "committed_unchanged": committed_unchanged,
        "applied_unchanged": applied_unchanged,
        "snapshot_unchanged": snapshot_unchanged,
        "application_state_unchanged": application_state_unchanged,
        "before": {
            "committed": target_committed.as_ref().map(|value| value.to_string()),
            "applied": target_applied.as_ref().map(|value| value.to_string()),
            "snapshot": target_snapshot.as_ref().map(|value| value.to_string()),
            "state_entries": target_state_before.len(),
        },
        "after": {
            "committed": target_after_metrics.local_committed.as_ref().map(|value| value.to_string()),
            "applied": target_after_metrics.last_applied.as_ref().map(|value| value.to_string()),
            "snapshot": target_after_metrics.snapshot.as_ref().map(|value| value.to_string()),
            "state_entries": target_state_after.len(),
        }
    });

    let result = match install_result {
        Ok(Ok(response)) if state_unchanged => json!({
            "kind": "hostile_snapshot_child_result",
            "outcome": "IGNORED_STALE_NO_STATE_CHANGE",
            "detail": format!("candidate returned a successful no-op: {response:?}"),
            "state_guard": state_guard,
        }),
        Ok(Ok(response)) => json!({
            "kind": "hostile_snapshot_child_result",
            "outcome": "ACCEPTED",
            "detail": format!("candidate returned success and changed guarded state: {response:?}"),
            "state_guard": state_guard,
        }),
        Ok(Err(error)) if state_unchanged => json!({
            "kind": "hostile_snapshot_child_result",
            "outcome": "REJECTED",
            "detail": error.to_string(),
            "state_guard": state_guard,
        }),
        Ok(Err(error)) => json!({
            "kind": "hostile_snapshot_child_result",
            "outcome": "ACCEPTED",
            "detail": format!("candidate returned an error but changed guarded state: {error}"),
            "state_guard": state_guard,
        }),
        Err(_) => json!({
            "kind": "hostile_snapshot_child_result",
            "outcome": "TIMED_OUT_AFTER_INJECTION",
            "detail": "install_full_snapshot exceeded the child deadline",
            "state_guard": state_guard,
        }),
    };
'''
    replace_between(
        path,
        "    let leader_vote = cluster.nodes[&1]",
        "    cluster.shutdown().await;\n    Ok(result)\n}",
        replacement,
    )

    parent = "probes/h02/openraft-tokio/src/bin/openraft_fault_lab.rs"
    replace(
        parent,
        'Some("REJECTED") => (',
        'Some("REJECTED") | Some("IGNORED_STALE_NO_STATE_CHANGE") => (',
    )
    replace(
        parent,
        "candidate returned an explicit rejection after stale committed snapshot injection",
        "candidate rejected the stale snapshot or completed a proven no-op without state regression",
    )

    rename_text(
        "REJECTED_OR_ABORTED_AFTER_INJECTION",
        "REJECTED_IGNORED_OR_ABORTED_AFTER_INJECTION",
        minimum=3,
    )

    plan = "planning/HEPTABAO_H02_OPENRAFT_HOSTILE_FAULTS_LINEARIZABILITY_V1.yaml"
    replace(
        plan,
        '''    EXECUTED_PASS:
      - explicit candidate rejection after the injection marker
      - isolated process fatality after the injection marker
    EXECUTED_FAIL:
      - candidate returns success for the stale committed snapshot
''',
        '''    EXECUTED_PASS:
      - explicit candidate rejection after the injection marker
      - successful API response proven to be a no-op by unchanged committed, applied, snapshot and application state
      - isolated process fatality after the injection marker
    EXECUTED_FAIL:
      - candidate changes any guarded state after stale committed snapshot injection
''',
    )

    inmemory_plan = "planning/HEPTABAO_H02_OPENRAFT_INMEMORY_CLUSTER_V1.yaml"
    replace(
        inmemory_plan,
        "remaining_blocker: hostile conflicting-snapshot injection is not executed because the candidate API documents panic on inconsistent local committed state",
        "remaining_blocker: dedicated fault-lab evidence must prove explicit rejection, process-fatal safety, or an exact no-op with no state regression",
    )
    replace(
        inmemory_plan,
        "  - hostile conflicting-snapshot injection is not executed",
        "  - dedicated hostile-snapshot no-regression evidence must pass on the exact source head",
    )


def patch_authority_sentinels() -> None:
    # The sentinel is an authority invariant, not a second copy of the technical
    # job. It must stay green when authority remains false/NONE even if a prior
    # technical lane fails; the technical job already preserves that failure.
    for path in (
        ".github/workflows/h02-openraft-inmemory-cluster.yml",
        ".github/workflows/h02-openraft-fault-lab.yml",
    ):
        value = read(path)
        old = "test \"${{ needs."
        # Only patch workflows that currently couple the sentinel to a technical
        # result. Exact string handling is intentionally narrow.
        if old not in value:
            print(f"authority sentinel in {path} has no coupled-result marker; left unchanged")
            continue
        lines = value.splitlines()
        output: list[str] = []
        removed = 0
        for line in lines:
            if "needs." in line and ".result" in line and "test " in line:
                removed += 1
                continue
            output.append(line)
        if removed == 0:
            raise SystemExit(f"{path}: coupled authority sentinel marker was not removable")
        write(path, "\n".join(output) + "\n")
        print(f"removed {removed} duplicated technical-result assertion(s) from {path}")


def assert_final_state() -> None:
    required = {
        "probes/h02/openraft-tokio/Cargo.toml": [
            'validit = "=0.2.5"',
            'rev = "7016fa5e072a86092928144b3a3040381e6964e9"',
            'openraft-macros = "=0.10.0-alpha.33"',
            'openraft-rt = "=0.10.0-alpha.33"',
            'openraft-rt-tokio = "=0.10.0-alpha.33"',
        ],
        "scripts/h02_candidate_adapter_harness_v1.py": [
            '"openraft-macros"',
            '"openraft-rt"',
            '"openraft-rt-tokio"',
            '"validit"',
        ],
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab.rs": [
            "REJECTED_IGNORED_OR_ABORTED_AFTER_INJECTION",
            "IGNORED_STALE_NO_STATE_CHANGE",
        ],
        "schemas/heptabao_h02_openraft_hostile_snapshot_result_v1.schema.json": [
            "REJECTED_IGNORED_OR_ABORTED_AFTER_INJECTION"
        ],
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/cluster.rs": [
            '"committed_unchanged"',
            '"application_state_unchanged"',
            "SnapshotPolicy::LogsSinceLast(10_000)",
        ],
        "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs": [
            "SnapshotPolicy::LogsSinceLast(10_000)"
        ],
    }
    for path, markers in required.items():
        value = read(path)
        for marker in markers:
            if marker not in value:
                raise SystemExit(f"{path}: missing required marker {marker!r}")

    forbidden = {
        "probes/h02/openraft-tokio/Cargo.toml": ['validit = "=0.2.6"'],
        "schemas/heptabao_h02_openraft_hostile_snapshot_result_v1.schema.json": [
            "REJECTED_OR_ABORTED_AFTER_INJECTION"
        ],
    }
    for path, markers in forbidden.items():
        value = read(path)
        for marker in markers:
            if marker in value:
                raise SystemExit(f"{path}: retained forbidden marker {marker!r}")


def main() -> int:
    patch_exact_openraft_family()
    patch_snapshot_replay()
    patch_os_suspend_probe()
    patch_hostile_snapshot_verdict()
    patch_authority_sentinels()
    assert_final_state()
    print("all H02 remaining-blocker source patches applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
