#!/usr/bin/env python3
"""Validate the final V1.3.1 repository-controlled closure inputs."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


class FinalClosureValidationError(RuntimeError):
    """Raised when final repository-closure semantics drift or overclaim."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise FinalClosureValidationError(message)


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    require(path.is_file(), f"missing final-closure file: {relative}")
    return path.read_text(encoding="utf-8")


def read_yaml(root: Path, relative: str) -> dict[str, Any]:
    value = yaml.safe_load(read_text(root, relative))
    require(isinstance(value, dict), f"{relative} must contain one mapping")
    return value


def require_tokens(text: str, tokens: tuple[str, ...], label: str) -> None:
    missing = [token for token in tokens if token not in text]
    require(not missing, f"{label} missing markers: {missing}")


def validate(root: Path) -> None:
    root = root.resolve()
    status = read_yaml(root, "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml")
    require(
        status.get("schema") == "heptabao.v1-3-1-final-closure-input.v1",
        "final closure schema drift",
    )
    require(status.get("revision") == "1.3.1-final-closure", "revision drift")
    integration = status.get("canonical_integration")
    require(isinstance(integration, dict), "canonical integration missing")
    require(integration.get("pull_request") == 45, "canonical PR drift")
    require(
        integration.get("source_identity")
        == "RESOLVE_FROM_EVENT_AND_GIT_NOT_FROM_STATIC_DOCUMENT",
        "source identity must be resolved from execution",
    )
    require(
        integration.get("synthetic_merge_identity")
        == "RESOLVE_FROM_PULL_REQUEST_EVENT_AND_VERIFY_TWO_PARENTS",
        "synthetic merge identity must be event and ancestry bound",
    )

    closure = status.get("repository_controlled_closure")
    require(isinstance(closure, dict), "repository closure mapping missing")
    require(closure.get("p0_runtime_observed_cases") == 11, "P0 runtime count drift")
    require(
        closure.get("p0_exact_head_compiled_source_bound_cases") == 2,
        "P0 compiled source-bound count drift",
    )
    require(
        closure.get("p0_best_effort_source_bound_cases") == 1,
        "P0 best-effort source-bound count drift",
    )
    for key in (
        "p0_runtime_vs_source_evidence_classification",
        "h02_legacy_log_bytes_vote_commit_entries_membership_equivalence",
        "h02_legacy_log_reopen_reader_replay",
        "h02_legacy_state_applied_membership_reopen_equivalence",
        "exact_head_and_distinct_synthetic_merge_workflow",
        "machine_readable_technical_receipt",
    ):
        require(closure.get(key) == "IMPLEMENTED_SOURCE", f"{key} is not implemented")
    require(
        closure.get("ordinary_owner_source_ratification") == "REQUIRED_FINAL_COMMIT",
        "owner ratification must be verified at exact head rather than self-asserted",
    )

    external = status.get("external_open")
    require(
        external
        == [
            "HB-BLK-CTRL-001",
            "HB-BLK-EXT-001",
            "HB-BLK-EXT-002",
            "HB-BLK-EXT-003",
            "HB-BLK-EXT-004",
            "HB-BLK-EXT-005",
            "HB-BLK-EXT-006",
            "HB-BLK-EXT-007",
        ],
        "external blocker coverage drift",
    )
    claims = status.get("claims")
    require(isinstance(claims, dict), "claims mapping missing")
    require(claims.get("qualification") is False, "qualification drift")
    require(claims.get("compatibility_claim") is False, "compatibility drift")
    require(claims.get("selected_candidates") == [], "selection drift")
    require(claims.get("selection_effect") == "NONE", "selection effect drift")
    require(claims.get("production_authority") is False, "production authority drift")
    require(claims.get("migration_authority") is False, "migration authority drift")
    require(claims.get("release_authority") is False, "release authority drift")
    require(claims.get("authority_effect") == "NONE", "authority effect drift")

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
    cases = matrix.get("cases")
    require(isinstance(cases, list) and len(cases) == 14, "P0 matrix count drift")
    by_id = {
        case.get("id"): case
        for case in cases
        if isinstance(case, dict) and isinstance(case.get("id"), str)
    }
    require(len(by_id) == 14, "P0 matrix IDs missing or duplicated")
    expected_runtime = {f"P0-TRANSPORT-{index:03d}" for index in range(1, 11)} | {
        "P0-TRANSPORT-013"
    }
    expected_compiled = {"P0-TRANSPORT-011", "P0-TRANSPORT-012"}
    expected_best_effort = {"P0-TRANSPORT-014"}
    require(
        {
            case_id
            for case_id, case in by_id.items()
            if case.get("evidence_class") == "RUNTIME_SOCKET_OBSERVED"
        }
        == expected_runtime,
        "runtime-observed P0 case classification drift",
    )
    require(
        {
            case_id
            for case_id, case in by_id.items()
            if case.get("evidence_class") == "EXACT_HEAD_COMPILED_SOURCE_BOUND"
        }
        == expected_compiled,
        "compiled source-bound P0 case classification drift",
    )
    require(
        {
            case_id
            for case_id, case in by_id.items()
            if case.get("evidence_class")
            == "BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND"
        }
        == expected_best_effort,
        "best-effort source-bound P0 case classification drift",
    )
    semantics = matrix.get("evidence_semantics")
    require(isinstance(semantics, dict), "P0 evidence semantics missing")
    require(
        semantics.get("source_presence_is_runtime_execution") is False,
        "source presence cannot become runtime evidence",
    )
    require(
        matrix.get("exact_head_requirements", {}).get(
            "classified_evidence_v2_required"
        )
        is True,
        "classified P0 evidence must be required",
    )

    classifier = read_text(root, "scripts/classify_p0_transport_evidence_v1.py")
    require_tokens(
        classifier,
        (
            '"RUNTIME_SOCKET_OBSERVED"',
            '"EXACT_HEAD_COMPILED_SOURCE_BOUND"',
            '"BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND"',
            '"executed_pass": len(RUNTIME_OBSERVED)',
            '"source_presence_is_runtime_execution": False',
            '"heptabao.p0-transport-exact-result.v2"',
        ),
        "P0 evidence classifier",
    )
    evidence_validator = read_text(
        root, "scripts/validate_p0_transport_evidence_v2.py"
    )
    require_tokens(
        evidence_validator,
        (
            'counts["executed_pass"] == 11',
            'case.get("evidence_class") == evidence_class',
            'source.get("commit") == expected_commit',
            'report.get("qualification") is False',
            'report.get("authority_effect") == "NONE"',
        ),
        "P0 evidence validator",
    )

    durable = read_text(
        root, "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs"
    )
    require_tokens(
        durable,
        (
            "async fn log_semantic_snapshot(",
            "store.get_log_state().await?",
            "store.read_vote().await?",
            "store.read_committed().await?",
            "store.try_get_log_entries(..).await?",
            "legacy_log_bytes_match",
            "let legacy_log_vote_matches = semantic_field_matches(",
            "legacy_log_committed_matches",
            "legacy_log_entries_match",
            "legacy_log_membership_matches",
            "legacy_log_reopen_matches",
            "legacy_state_last_applied_matches",
            "legacy_state_membership_matches",
            "legacy_state_reopen_matches",
            '"explicit_legacy_log_semantics_verified": true',
            '"explicit_legacy_state_membership_verified": true',
        ),
        "H02 legacy-adoption evidence",
    )

    workflow = read_text(
        root, ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml"
    )
    require_tokens(
        workflow,
        (
            "source_kind: ${{ fromJSON",
            "github.event_name == 'pull_request'",
            "matrix.source_kind == 'merge' && github.sha",
            "test \"$SOURCE_SHA\" != \"$HEAD_SHA\"",
            "git rev-list --parents -n 1 HEAD",
            "test \"$parent_one\" = \"$BASE_SHA\"",
            "test \"$parent_two\" = \"$HEAD_SHA\"",
            "chore(provenance): owner-ratify V1.3.1 canonical source tree",
            "*github-actions*",
            "cargo +1.98.0 fmt --all -- --check",
            "cargo +1.98.0 test --locked --workspace --all-targets",
            "cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings",
            "scripts/classify_p0_transport_evidence_v1.py",
            "scripts/validate_p0_transport_evidence_v2.py",
            "scripts/h02_exact_head_matrix_v1.py",
            'summary["matrix"]["executed_entry_count"] == 24',
            'p0["counts"]["executed_pass"] == 11',
            '"qualification": False',
            '"authority_effect": "NONE"',
            "runs-on: ubuntu-24.04",
        ),
        "head and synthetic-merge closure workflow",
    )
    for forbidden in (
        "contents: write",
        "persist-credentials: true",
        "git push",
        "git commit",
        "ubuntu-slim",
    ):
        require(forbidden not in workflow, f"forbidden workflow marker: {forbidden}")

    protocol = read_text(
        root, "docs/execution/HEPTABAO_V1_3_1_FINAL_CLOSURE_PROTOCOL.md"
    )
    require_tokens(
        protocol,
        (
            "11 entries are `RUNTIME_SOCKET_OBSERVED`",
            "two entries are `EXACT_HEAD_COMPILED_SOURCE_BOUND`",
            "one entry is `BEST_EFFORT_CONTROLLED_DROP_SOURCE_BOUND`",
            "GitHub's synthetic merge commit",
            "persisted vote",
            "retained membership entries",
            "External boundary",
        ),
        "final closure protocol",
    )

    manifest = read_yaml(
        root, "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3_1.yaml"
    )
    documents = manifest.get("documents")
    require(isinstance(documents, list), "V1.3.1 manifest documents missing")
    paths = {
        entry.get("path")
        for entry in documents
        if isinstance(entry, dict) and isinstance(entry.get("path"), str)
    }
    for path in (
        "planning/HEPTABAO_V1_3_1_FINAL_CLOSURE_INPUT.yaml",
        "docs/execution/HEPTABAO_V1_3_1_FINAL_CLOSURE_PROTOCOL.md",
        "scripts/classify_p0_transport_evidence_v1.py",
        "scripts/validate_p0_transport_evidence_v2.py",
        "scripts/validate_v1_3_1_final_closure_v1.py",
        "tests/plan/test_p0_transport_evidence_classification_v2.py",
        "tests/plan/test_v1_3_1_final_closure.py",
        ".github/workflows/plan-v1.3.1-head-and-merge-closure.yml",
    ):
        require(path in paths, f"final closure manifest missing: {path}")
    require(manifest.get("qualification") is False, "manifest qualification drift")
    require(
        manifest.get("compatibility_claim") is False,
        "manifest compatibility drift",
    )
    require(manifest.get("authority_effect") == "NONE", "manifest authority drift")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parents[1]
    )
    args = parser.parse_args()
    try:
        validate(args.root)
    except (OSError, yaml.YAMLError, FinalClosureValidationError) as error:
        print(f"HeptaBao V1.3.1 final closure validation FAILED: {error}")
        return 1
    print(
        "HeptaBao V1.3.1 final closure validation passed: "
        "P0 evidence classified; H02 legacy semantics bound; head+merge gates required; "
        "qualification=false authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
