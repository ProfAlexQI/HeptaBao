#!/usr/bin/env python3
"""Validate current repository identity without rewriting historical lineage.

The repository may move between owners while retaining the same stable GitHub
repository ID.  Current execution artifacts therefore bind both the stable ID
and the current full name.  The designated source ratifier is a separate human
account and must never be inferred from the repository owner.

Historical ``ProfHepta/HeptaBao`` records remain audit lineage only.  They may
exist in inherited documents and old evidence schemas, but no current execution
surface or current receipt schema may emit or accept that name.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CURRENT_REPOSITORY_ID = 1_349_115_072
CURRENT_OWNER = "TrillionniumFoundation"
CURRENT_REPOSITORY = f"{CURRENT_OWNER}/HeptaBao"
HISTORICAL_REPOSITORY = "ProfHepta/HeptaBao"
DESIGNATED_RATIFIER_LOGIN = "ProfHepta"
DESIGNATED_RATIFIER_ACCOUNT_ID = 102_159_240
DEPRECATED_OWNER = "ProfAlex" + "QI"

CURRENT_SCHEMA_BINDINGS: dict[str, tuple[int, int]] = {
    # path: (minimum current-name const count, minimum repository-ID const count)
    "schemas/heptabao_v1_3_1_technical_completion_receipt_v1.schema.json": (2, 1),
    "schemas/heptabao_v1_3_1_lane_arbitration_v1.schema.json": (1, 0),
    "schemas/heptabao_h02_exact_head_matrix_summary_v1.schema.json": (1, 0),
}

CURRENT_EXECUTION_SURFACES = (
    ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml",
    "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml",
    "scripts/arbitrate_v1_3_1_lanes_v1.py",
    "scripts/classify_p0_transport_evidence_v1.py",
    "scripts/collect_github_job_identity_v1.py",
    "scripts/h02_exact_head_matrix_v1.py",
    "scripts/p0_transport_exact_core_v1.py",
    "scripts/validate_p0_transport_evidence_v2.py",
    "scripts/validate_v1_3_1_technical_completion_receipt_v1_core.py",
)

REQUIRED_PATHS = tuple(
    sorted(
        set(CURRENT_SCHEMA_BINDINGS)
        | set(CURRENT_EXECUTION_SURFACES)
        | {
            ".github/CODEOWNERS",
            "docs/execution/HEPTABAO_V1_3_1_FINAL_CLOSURE_PROTOCOL.md",
            "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
        }
    )
)

YAML_SCALAR_PATTERN = re.compile(
    r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_]*):(?:[ ](?P<value>.*))?$"
)
WORKFLOW_IDENTITY_PATTERN = re.compile(
    r"^[ ]+(?P<key>EXPECTED_(?:REPOSITORY_ID|REPOSITORY|HEAD_OWNER|RATIFIER_LOGIN|RATIFIER_ID)):[ ]+(?P<value>.+?)\s*$",
    re.MULTILINE,
)



class IdentityFailure(RuntimeError):
    """A current repository identity invariant did not hold."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise IdentityFailure(message)


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    try:
        return path.read_text(encoding="utf-8")
    except OSError as error:
        raise IdentityFailure(f"cannot read {relative}: {error}") from error


def _strict_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in pairs:
        if key in value:
            raise ValueError(f"duplicate JSON key: {key!r}")
        value[key] = item
    return value


def _reject_json_constant(value: str) -> None:
    raise ValueError(f"non-finite JSON number is forbidden: {value}")


def read_json(root: Path, relative: str) -> Any:
    try:
        return json.loads(
            read_text(root, relative),
            object_pairs_hook=_strict_json_pairs,
            parse_constant=_reject_json_constant,
        )
    except (json.JSONDecodeError, ValueError) as error:
        raise IdentityFailure(f"{relative}: invalid strict JSON: {error}") from error


def parse_yaml_scalar(raw: str | None) -> Any:
    require(raw is not None and raw.strip() != "", "required YAML scalar is empty")
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] == "'":
        return value[1:-1].replace("''", "'")
    if len(value) >= 2 and value[0] == value[-1] == '"':
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as error:
            raise IdentityFailure(f"invalid quoted YAML scalar: {error}") from error
        require(isinstance(decoded, str), "quoted YAML scalar must decode to text")
        return decoded
    if value == "true":
        return True
    if value == "false":
        return False
    if value == "null":
        return None
    if value.isascii() and value.isdigit():
        return int(value)
    return value


def parse_yaml_mapping_section(text: str, section: str) -> dict[str, Any]:
    lines = text.splitlines()
    headers = [index for index, line in enumerate(lines) if line == f"{section}:"]
    require(len(headers) == 1, f"YAML section {section!r} must occur exactly once")
    result: dict[str, Any] = {}
    for line in lines[headers[0] + 1 :]:
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if indent == 0:
            break
        match = YAML_SCALAR_PATTERN.fullmatch(line)
        if match is None or indent != 2:
            continue
        key = match.group("key")
        require(key not in result, f"duplicate key in YAML section {section}: {key}")
        raw = match.group("value")
        result[key] = None if raw is None else parse_yaml_scalar(raw)
    require(result, f"YAML section {section!r} is empty or malformed")
    return result


def parse_workflow_identity_environment(text: str) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for match in WORKFLOW_IDENTITY_PATTERN.finditer(text):
        key = match.group("key")
        require(key not in result, f"duplicate canonical workflow identity variable: {key}")
        result[key] = parse_yaml_scalar(match.group("value"))
    return result


FALLBACK_IGNORED_COMPONENTS = frozenset(
    {
        ".git",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        "__pycache__",
        "target",
    }
)
FALLBACK_IGNORED_SUFFIXES = frozenset({".pyc", ".pyo"})


def _fallback_source_paths(root: Path) -> list[Path]:
    """Enumerate source-archive files without admitting generated caches.

    A Git checkout uses ``git ls-files`` as the canonical tracked-file set.  An
    exact-source export intentionally omits ``.git``, so the fallback must be
    deterministic and must not let Python bytecode, test caches or Rust build
    output alter identity validation after tools execute in the extracted tree.
    """

    result: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(component in FALLBACK_IGNORED_COMPONENTS for component in relative.parts):
            continue
        if path.suffix in FALLBACK_IGNORED_SUFFIXES:
            continue
        if path.is_symlink():
            raise IdentityFailure(
                f"source-archive identity scan refuses symlink: {relative.as_posix()}"
            )
        result.append(path)
    return sorted(result, key=lambda item: item.relative_to(root).as_posix())


def tracked_paths(root: Path) -> list[Path]:
    try:
        payload = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=root, stderr=subprocess.DEVNULL
        )
    except (OSError, subprocess.CalledProcessError):
        return _fallback_source_paths(root)
    return [root / item.decode("utf-8") for item in payload.split(b"\0") if item]


def collect_consts(value: Any) -> list[Any]:
    result: list[Any] = []
    if isinstance(value, dict):
        if "const" in value:
            result.append(value["const"])
        for child in value.values():
            result.extend(collect_consts(child))
    elif isinstance(value, list):
        for child in value:
            result.extend(collect_consts(child))
    return result


def validate_no_deprecated_owner(root: Path) -> int:
    deprecated = DEPRECATED_OWNER.encode("utf-8")
    offenders: list[str] = []
    paths = tracked_paths(root)
    for path in paths:
        try:
            payload = path.read_bytes()
        except OSError as error:
            raise IdentityFailure(
                f"cannot read tracked path {path.relative_to(root)}: {error}"
            ) from error
        if deprecated in payload:
            offenders.append(path.relative_to(root).as_posix())
    require(
        not offenders,
        "deprecated owner identity remains in: " + ", ".join(sorted(offenders)),
    )
    return len(paths)


def validate_current_schema_bindings(root: Path) -> None:
    for relative, (minimum_name_count, minimum_id_count) in CURRENT_SCHEMA_BINDINGS.items():
        consts = collect_consts(read_json(root, relative))
        require(
            HISTORICAL_REPOSITORY not in consts,
            f"{relative}: historical repository name is accepted by a current schema",
        )
        require(
            consts.count(CURRENT_REPOSITORY) >= minimum_name_count,
            f"{relative}: current repository full-name binding is missing",
        )
        require(
            consts.count(CURRENT_REPOSITORY_ID) >= minimum_id_count,
            f"{relative}: stable repository-ID binding is missing",
        )


def validate_current_execution_surfaces(root: Path) -> None:
    for relative in CURRENT_EXECUTION_SURFACES:
        value = read_text(root, relative)
        require(
            HISTORICAL_REPOSITORY not in value,
            f"{relative}: historical repository name leaked into current execution",
        )
        require(
            CURRENT_REPOSITORY in value,
            f"{relative}: current repository full name is not bound",
        )

    workflow = read_text(root, ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml")
    environment = parse_workflow_identity_environment(workflow)
    expected_environment = {
        "EXPECTED_REPOSITORY_ID": str(CURRENT_REPOSITORY_ID),
        "EXPECTED_REPOSITORY": CURRENT_REPOSITORY,
        "EXPECTED_HEAD_OWNER": "${{ github.event.pull_request.head.repo.owner.login || github.repository_owner }}",
        "EXPECTED_RATIFIER_LOGIN": DESIGNATED_RATIFIER_LOGIN,
        "EXPECTED_RATIFIER_ID": str(DESIGNATED_RATIFIER_ACCOUNT_ID),
    }
    require(
        environment == expected_environment,
        f"canonical workflow identity environment drift: {environment!r}",
    )
    require(
        workflow.count("scripts/validate_repository_identity_v1.py") == 1,
        "canonical workflow must invoke the transfer-aware identity validator exactly once",
    )


def validate_final_closure_identity(root: Path) -> None:
    value = read_text(root, "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml")
    integration = parse_yaml_mapping_section(value, "canonical_integration")
    require(
        integration.get("repository_id") == CURRENT_REPOSITORY_ID,
        "final closure canonical_integration.repository_id drift",
    )
    require(
        integration.get("repository") == CURRENT_REPOSITORY,
        "final closure canonical_integration.repository drift",
    )
    require(
        integration.get("repository_owner") == CURRENT_OWNER,
        "final closure canonical_integration.repository_owner drift",
    )
    require(
        integration.get("source_identity")
        == "RESOLVE_FROM_EVENT_AND_GIT_NOT_FROM_STATIC_DOCUMENT",
        "final closure source identity resolution drift",
    )
    require(
        integration.get("synthetic_merge_identity")
        == "RESOLVE_FROM_PULL_REQUEST_EVENT_AND_VERIFY_TWO_PARENTS",
        "final closure synthetic merge identity resolution drift",
    )

    ratification = parse_yaml_mapping_section(value, "ratification_authenticity")
    require(
        ratification.get("designated_ratifier_login") == DESIGNATED_RATIFIER_LOGIN,
        "final closure designated ratifier login drift",
    )
    require(
        ratification.get("designated_ratifier_account_id")
        == DESIGNATED_RATIFIER_ACCOUNT_ID,
        "final closure designated ratifier account drift",
    )
    require(
        ratification.get("repository_owner_may_differ_from_ratifier") is True,
        "final closure repository_owner_may_differ_from_ratifier must remain true",
    )


def validate_documented_lineage(root: Path) -> None:
    for relative in (
        "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
        "docs/execution/HEPTABAO_V1_3_1_FINAL_CLOSURE_PROTOCOL.md",
    ):
        value = read_text(root, relative)
        require(CURRENT_REPOSITORY in value, f"{relative}: current repository not documented")
        require(HISTORICAL_REPOSITORY in value, f"{relative}: historical lineage not documented")
        require(
            DESIGNATED_RATIFIER_LOGIN in value,
            f"{relative}: designated ratifier separation not documented",
        )


def validate_codeowners_boundary(root: Path) -> None:
    value = read_text(root, ".github/CODEOWNERS")
    require(
        "Bootstrap ownership only" in value,
        "CODEOWNERS must explicitly remain bootstrap-only until independent teams exist",
    )
    require(
        "does not satisfy independent-review" in value,
        "CODEOWNERS must not claim to satisfy independent review",
    )
    require(
        f"* @{DESIGNATED_RATIFIER_LOGIN}" in value,
        "bootstrap CODEOWNERS entry for the designated repository steward is missing",
    )


def validate_repository_identity(root: Path = ROOT) -> int:
    root = Path(root)
    require(root.is_dir(), f"repository root is missing: {root}")
    for relative in REQUIRED_PATHS:
        require((root / relative).is_file(), f"required identity surface is missing: {relative}")

    tracked_count = validate_no_deprecated_owner(root)
    validate_current_schema_bindings(root)
    validate_current_execution_surfaces(root)
    validate_final_closure_identity(root)
    validate_documented_lineage(root)
    validate_codeowners_boundary(root)
    return tracked_count


def main(argv: Iterable[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if len(arguments) > 1:
        print("usage: validate_repository_identity_v1.py [REPOSITORY_ROOT]", file=sys.stderr)
        return 2
    root = Path(arguments[0]).resolve() if arguments else ROOT
    try:
        tracked_count = validate_repository_identity(root)
    except (IdentityFailure, OSError) as error:
        print(f"repository identity validation FAILED: {error}", file=sys.stderr)
        return 1

    print(
        "repository identity validation passed: "
        f"repository_id={CURRENT_REPOSITORY_ID} "
        f"current={CURRENT_REPOSITORY} "
        f"historical={HISTORICAL_REPOSITORY} "
        f"ratifier={DESIGNATED_RATIFIER_LOGIN}/{DESIGNATED_RATIFIER_ACCOUNT_ID} "
        f"tracked_files={tracked_count}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
