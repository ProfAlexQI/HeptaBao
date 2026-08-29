#!/usr/bin/env python3
"""Verify generated H02 closure outputs without granting qualification."""
from __future__ import annotations

import argparse
import json
import tomllib
from pathlib import Path
from typing import Any


def load_json(path: str) -> dict[str, Any]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise SystemExit(f"{path}: expected JSON object")
    return value


def verify_lock(path: str) -> None:
    value = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    by_name: dict[str, list[dict[str, Any]]] = {}
    for package in value.get("package", []):
        by_name.setdefault(str(package["name"]), []).append(package)

    def one(name: str) -> dict[str, Any]:
        found = by_name.get(name, [])
        if len(found) != 1:
            raise SystemExit(f"{path}: expected exactly one {name!r}, found {found!r}")
        return found[0]

    family = (
        "openraft",
        "openraft-macros",
        "openraft-memstore",
        "openraft-rt",
        "openraft-rt-tokio",
    )
    for name in family:
        package = one(name)
        if package.get("version") != "0.10.0-alpha.33":
            raise SystemExit(f"{path}: {name} family drift: {package!r}")

    validit = one("validit")
    if validit.get("version") != "0.2.5":
        raise SystemExit(f"{path}: validit version drift: {validit!r}")
    source = str(validit.get("source", ""))
    if not source.startswith("git+https://github.com/drmingdrmer/validit.git"):
        raise SystemExit(f"{path}: validit source is not the audited git repository: {source}")
    if "7016fa5e072a86092928144b3a3040381e6964e9" not in source:
        raise SystemExit(f"{path}: validit source is not bound to the audited commit: {source}")

    root = one("heptabao-h02-probe-openraft-tokio")
    direct = {str(item).split(" ", 1)[0] for item in root.get("dependencies", [])}
    expected = {
        "openraft",
        "openraft-macros",
        "openraft-memstore",
        "openraft-rt",
        "openraft-rt-tokio",
        "serde_json",
        "tokio",
        "validit",
    }
    missing = sorted(expected - direct)
    if missing:
        raise SystemExit(f"{path}: root package missing direct bindings: {missing}")
    print("Cargo.lock exact OpenRaft alpha.33 family and validit 0.2.5 binding: PASS")


def verify_inmemory(path: str) -> None:
    rows = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip().startswith("{"):
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            rows.append(value)
    summaries = [row for row in rows if row.get("kind") == "summary"]
    if len(summaries) != 1 or summaries[0].get("status") != "EXECUTED_PASS":
        raise SystemExit(f"{path}: in-memory summary did not pass: {summaries!r}")
    summary = summaries[0]
    for key, expected in (
        ("qualification", False),
        ("selection_effect", "NONE"),
        ("authority_effect", "NONE"),
    ):
        if summary.get(key) != expected:
            raise SystemExit(f"{path}: authority invariant drift: {key}={summary.get(key)!r}")
    print(f"{path}: in-memory OpenRaft execution PASS; authority=NONE")


def verify_hostile(path: str) -> None:
    value = load_json(path)
    if value.get("status") != "EXECUTED_PASS":
        raise SystemExit(f"{path}: hostile snapshot status: {value!r}")
    if value.get("outcome") != "REJECTED_IGNORED_OR_ABORTED_AFTER_INJECTION":
        raise SystemExit(f"{path}: hostile snapshot outcome: {value!r}")
    for key, expected in (
        ("qualification", False),
        ("selection_effect", "NONE"),
        ("authority_effect", "NONE"),
    ):
        if value.get(key) != expected:
            raise SystemExit(f"{path}: authority invariant drift: {key}={value.get(key)!r}")
    print(f"{path}: hostile snapshot no-regression execution PASS; authority=NONE")


def verify_blocker(path: str) -> None:
    value = load_json(path)
    if value.get("status") != "EXECUTED_PASS":
        raise SystemExit(f"{path}: blocker closure status: {value!r}")
    cases = value.get("cases", {})
    expected_cases = ("os_suspend_resume", "durable_wal", "clock_faults")
    for case in expected_cases:
        if not isinstance(cases.get(case), dict) or cases[case].get("status") != "PASS":
            raise SystemExit(f"{path}: {case} did not pass: {cases.get(case)!r}")
    for key, expected in (
        ("qualification", False),
        ("selection_effect", "NONE"),
        ("authority_effect", "NONE"),
    ):
        if value.get(key) != expected:
            raise SystemExit(f"{path}: authority invariant drift: {key}={value.get(key)!r}")
    print(f"{path}: OS/WAL/clock blocker execution PASS; authority=NONE")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("lock", "inmemory", "hostile", "blocker"):
        child = subparsers.add_parser(command)
        child.add_argument("path")
    args = parser.parse_args()
    {
        "lock": verify_lock,
        "inmemory": verify_inmemory,
        "hostile": verify_hostile,
        "blocker": verify_blocker,
    }[args.command](args.path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
