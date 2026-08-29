#!/usr/bin/env python3
"""Fail closed when evidence or ownership binds to a stale HeptaBao identity."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPECTED_OWNER = "ProfHepta"
EXPECTED_REPOSITORY = f"{EXPECTED_OWNER}/HeptaBao"
DEPRECATED_OWNER = "ProfAlex" + "QI"


class IdentityFailure(RuntimeError):
    pass


def fail(message: str) -> None:
    raise IdentityFailure(message)


def tracked_paths() -> list[Path]:
    try:
        payload = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=ROOT, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return sorted(path for path in ROOT.rglob("*") if path.is_file() and ".git" not in path.parts)
    return [ROOT / item.decode("utf-8") for item in payload.split(b"\0") if item]


def repository_const(path: str) -> str:
    value = json.loads((ROOT / path).read_text(encoding="utf-8"))
    try:
        return value["properties"]["source"]["properties"]["repository"]["const"]
    except (KeyError, TypeError) as error:
        fail(f"{path}: source.repository.const missing: {error}")


def main() -> int:
    try:
        deprecated = DEPRECATED_OWNER.encode("utf-8")
        offenders: list[str] = []
        paths = tracked_paths()
        for path in paths:
            try:
                payload = path.read_bytes()
            except OSError as error:
                fail(f"cannot read tracked path {path.relative_to(ROOT)}: {error}")
            if deprecated in payload:
                offenders.append(path.relative_to(ROOT).as_posix())
        if offenders:
            fail("deprecated owner identity remains in: " + ", ".join(sorted(offenders)))

        schemas = (
            "schemas/heptabao_dependency_probe_evidence_v1.schema.json",
            "schemas/heptabao_qualification_receipt_v2.schema.json",
        )
        for path in schemas:
            actual = repository_const(path)
            if actual != EXPECTED_REPOSITORY:
                fail(f"{path}: repository const {actual!r} != {EXPECTED_REPOSITORY!r}")

        collector = (ROOT / "scripts/h02_dependency_probe_v1.py").read_text(encoding="utf-8")
        if EXPECTED_REPOSITORY not in collector:
            fail("dependency probe collector is not bound to the canonical repository")

        fixture = (ROOT / "scripts/validate_plan_v2.py").read_text(encoding="utf-8")
        if EXPECTED_REPOSITORY not in fixture:
            fail("qualification schema fixture is not bound to the canonical repository")

        codeowners = (ROOT / ".github/CODEOWNERS").read_text(encoding="utf-8")
        if f"@{EXPECTED_OWNER}" not in codeowners:
            fail("CODEOWNERS is not bound to the canonical repository owner")
    except (IdentityFailure, OSError, json.JSONDecodeError) as error:
        print(f"repository identity validation FAILED: {error}", file=sys.stderr)
        return 1

    print(
        "repository identity validation passed: "
        f"repository={EXPECTED_REPOSITORY} tracked_files={len(paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
