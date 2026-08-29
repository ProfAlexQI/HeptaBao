#!/usr/bin/env python3
"""Apply the exact source fixes discovered by real H02 GitHub Runner executions.

This is a one-shot maintenance helper.  The invoking workflow removes this file
and itself before committing the verified source changes.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def replace_once(relative: str, old: str, new: str) -> None:
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != 1:
        raise RuntimeError(
            f"{relative}: expected exactly one occurrence, found {actual}: {old!r}"
        )
    path.write_text(text.replace(old, new), encoding="utf-8")
    print(f"patched {relative}")


def patch_operation_registry() -> None:
    path = ROOT / "specs/HEPTABAO_OPERATION_REGISTRY_V1.yaml"
    text = path.read_text(encoding="utf-8")
    operations = (
        "sys.health.read",
        "sys.mounts.update",
        "secret.dynamic.read",
        "auth.login",
        "token.create",
        "seal.unseal.submit-share",
        "cluster.join",
        "migration.cutover",
    )
    for operation_id in operations:
        old = f"  {operation_id}:\n    operation_class:"
        new = (
            f"  {operation_id}:\n"
            f"    operation_id: {operation_id}\n"
            "    operation_class:"
        )
        actual = text.count(old)
        if actual != 1:
            raise RuntimeError(
                f"operation registry {operation_id}: expected one insertion point, "
                f"found {actual}"
            )
        text = text.replace(old, new)
    path.write_text(text, encoding="utf-8")
    print("patched operation registry explicit identities")


def patch_rustls_fixtures() -> None:
    replace_once(
        "probes/h02/rustls-public-fixtures.rs",
        "0xae, 0xbg, 0x4b",
        "0xae, 0xb7, 0x4b",
    )
    replace_once(
        "probes/h02/rustls-public-fixtures.rs",
        "0x0f, 0x01, 0xff, 0x04, 0x04, 0x03",
        "0x0f, 0x01, 0x01, 0xff, 0x04, 0x04, 0x03",
    )


def patch_workspace_clippy() -> None:
    replace_once(
        "Cargo.toml",
        'all = "warn"',
        'all = { level = "warn", priority = -1 }',
    )
    replace_once(
        "crates/heptabao-platform-contracts/src/lib.rs",
        """        if let Some(applied) = cursor.last_applied {
            if self.last_included.index < applied.index {
                return Err(ContractError::SnapshotRegression);
            }
        }
""",
        """        if let Some(applied) = cursor.last_applied
            && self.last_included.index < applied.index
        {
            return Err(ContractError::SnapshotRegression);
        }
""",
    )


def patch_dependency_floors() -> None:
    replace_once(
        "probes/h02/openraft-tokio/Cargo.toml",
        'openraft-memstore = { version = "=0.10.0-alpha.33" }',
        'openraft-memstore = { version = "=0.10.0-alpha.33" }\n'
        'validit = "=0.2.5"',
    )
    replace_once(
        "probes/h02/rustls-ring/Cargo.toml",
        'rustls = { version = "=0.23.43", default-features = false, '
        'features = ["logging", "ring", "std", "tls12"] }',
        'rustls = { version = "=0.23.43", default-features = false, '
        'features = ["logging", "ring", "std", "tls12"] }\n'
        'zeroize = "=1.8.2"',
    )
    replace_once(
        "probes/h02/rustls-aws-lc/Cargo.toml",
        'rustls = { version = "=0.23.43", default-features = false, '
        'features = ["aws_lc_rs", "logging", "prefer-post-quantum", '
        '"std", "tls12"] }',
        'rustls = { version = "=0.23.43", default-features = false, '
        'features = ["aws_lc_rs", "logging", "prefer-post-quantum", '
        '"std", "tls12"] }\n'
        'zeroize = "=1.8.2"\n'
        'jobserver = "=0.1.32"',
    )


def patch_openraft_sources() -> None:
    for relative in (
        "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs",
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/cluster.rs",
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/os_clock_cluster.rs",
    ):
        replace_once(relative, "enable_pre_vote: true,", "enable_pre_vote: Some(true),")
    replace_once(
        "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs",
        "!matches!(old_write, Ok(Ok(Ok(_))))",
        "!matches!(old_write, Ok(Ok(_)))",
    )
    replace_once(
        "probes/h02/openraft-tokio/src/bin/inmemory_cluster/cluster.rs",
        "!matches!(result, Ok(Ok(Ok(_))))",
        "!matches!(result, Ok(Ok(_)))",
    )
    replace_once(
        "probes/h02/openraft-tokio/src/bin/openraft_fault_lab/os_clock_cluster.rs",
        "use openraft::async_runtime::WatchReceiver;\n",
        "",
    )


def patch_serial_validator_contracts() -> None:
    replace_once(
        "scripts/validate_h02_openraft_inmemory_cluster_v1.py",
        '            "fail-fast: false",',
        '            "Execute all six entries serially and retain every outcome",\n'
        '            "exit 0",',
    )
    replace_once(
        "scripts/validate_h02_openraft_fault_lab_v1.py",
        '            "fail-fast: false",',
        '            "Execute all six fault-lab entries and retain every outcome", '
        '"exit 0",',
    )


def patch_probe_fixture_copy() -> None:
    path = ROOT / ".github/workflows/h02-probe-sbom-msrv.yml"
    text = path.read_text(encoding="utf-8")
    copy_line = (
        '          cp probes/h02/rustls-public-fixtures.rs '
        '"$RUNNER_TEMP/rustls-public-fixtures.rs"\n'
    )
    marker = '          git rev-parse "$GITHUB_SHA" > "$RUNNER_TEMP/source-commit.txt"\n'
    if copy_line in text or text.count(marker) != 1:
        raise RuntimeError("probe workflow fixture-copy insertion point drift")
    path.write_text(text.replace(marker, copy_line + marker), encoding="utf-8")
    print("patched probe workflow shared rustls fixture copy")


def patch_blocker_closure_runner_context() -> None:
    path = ROOT / ".github/workflows/h02-openraft-blocker-closure.yml"
    text = path.read_text(encoding="utf-8")
    filtered: list[str] = []
    removed = 0
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        if stripped.startswith(("EVIDENCE_ROOT:", "PROBE_ROOT:")) and "runner.temp" in stripped:
            removed += 1
            continue
        filtered.append(line)
    if removed != 2:
        raise RuntimeError(
            f"blocker closure workflow: expected two invalid runner.temp env lines, "
            f"removed {removed}"
        )
    text = "".join(filtered)
    pip_step = (
        "      - run: python -m pip install --disable-pip-version-check "
        "--requirement requirements-plan.txt\n"
    )
    bind_step = """      - name: Bind runner-local evidence roots
        shell: bash
        run: |
          printf 'EVIDENCE_ROOT=%s\\n' "$RUNNER_TEMP/h02-blocker-closure-evidence" >> "$GITHUB_ENV"
          printf 'PROBE_ROOT=%s\\n' "$RUNNER_TEMP/h02-blocker-closure-probes" >> "$GITHUB_ENV"
"""
    if text.count(pip_step) != 1:
        raise RuntimeError("blocker closure workflow pip insertion point drift")
    path.write_text(text.replace(pip_step, bind_step + pip_step), encoding="utf-8")
    print("patched blocker closure runner-local environment binding")


def main() -> int:
    patch_operation_registry()
    patch_rustls_fixtures()
    patch_workspace_clippy()
    patch_dependency_floors()
    patch_openraft_sources()
    patch_serial_validator_contracts()
    patch_probe_fixture_copy()
    patch_blocker_closure_runner_context()
    print("all runner-discovered H02 source patches applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
