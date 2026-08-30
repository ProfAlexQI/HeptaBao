#!/usr/bin/env python3
"""Validate the V1.3.1 repository-controlled gap-closure contract."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


class ValidationError(RuntimeError):
    """Raised when a fail-closed V1.3.1 invariant is violated."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def read_text(root: Path, relative: str) -> str:
    path = root / relative
    require(path.is_file(), f"missing required file: {relative}")
    return path.read_text(encoding="utf-8")


def read_yaml(root: Path, relative: str) -> dict[str, Any]:
    value = yaml.safe_load(read_text(root, relative))
    require(isinstance(value, dict), f"{relative} must contain one mapping")
    return value


def require_tokens(text: str, tokens: list[str], label: str) -> None:
    missing = [token for token in tokens if token not in text]
    require(not missing, f"{label} missing markers: {missing}")


def validate(root: Path) -> None:
    root = root.resolve()
    status_path = "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml"
    status = read_yaml(root, status_path)
    require(status.get("schema") == "heptabao.v1-3-1-gap-closure-status.v1", "status schema drift")
    require(status.get("revision") == "1.3.1", "status revision drift")
    integration = status.get("canonical_integration")
    require(isinstance(integration, dict), "canonical integration missing")
    require(integration.get("branch") == "codex/plan-v1.3-gap-closure-v2", "canonical branch drift")
    require(integration.get("pull_request") == 45, "canonical pull request drift")
    require(integration.get("ordinary_reviewable_source") is True, "ordinary source must remain true")
    require(
        integration.get("compressed_transport_is_not_canonical_delivery") is True,
        "compressed source transport cannot become canonical delivery",
    )

    remediation = status.get("repository_remediation")
    require(isinstance(remediation, dict), "repository remediation missing")
    expected_remediation = {
        "total_request_read_deadline",
        "bounded_concurrent_connections",
        "preparse_request_attempt_identity",
        "transport_rejection_audit",
        "client_request_id_duplicate_guard",
        "http_204_zero_wire_body",
        "durable_active_parent_fail_closed",
        "legacy_data_temporary_artifact_guard",
        "exact_head_consolidated_workflow",
        "machine_checked_v1_3_1_contract",
    }
    require(set(remediation) == expected_remediation, "repository remediation coverage drift")
    require(
        all(str(value).startswith("IMPLEMENTED") for value in remediation.values()),
        "source remediation must remain explicitly implemented",
    )

    execution = status.get("execution_required")
    require(isinstance(execution, dict) and execution, "execution requirements missing")
    require(
        all(value in {"REQUIRED_EXACT_HEAD", "REQUIRED_EXTERNAL_IDENTITY"} for value in execution.values()),
        "execution cannot be pre-closed in source",
    )

    expected_external = {
        "HB-BLK-CTRL-001",
        "HB-BLK-EXT-001",
        "HB-BLK-EXT-002",
        "HB-BLK-EXT-003",
        "HB-BLK-EXT-004",
        "HB-BLK-EXT-005",
        "HB-BLK-EXT-006",
        "HB-BLK-EXT-007",
    }
    external = status.get("external_open")
    require(isinstance(external, list), "external blocker list missing")
    external_ids = {entry.get("id") for entry in external if isinstance(entry, dict)}
    require(external_ids == expected_external, "external blocker coverage drift")
    require(
        all(entry.get("state") == "EXTERNAL_ACTION_REQUIRED" for entry in external),
        "external blocker cannot be self-closed",
    )

    claims = status.get("claims")
    require(isinstance(claims, dict), "claims mapping missing")
    require(claims.get("qualification") is False, "qualification authority drift")
    require(claims.get("compatibility_claim") is False, "compatibility authority drift")
    require(claims.get("selected_candidates") == [], "candidate selection drift")
    require(claims.get("selection_effect") == "NONE", "selection effect drift")
    require(claims.get("production_authority") is False, "production authority drift")
    require(claims.get("migration_authority") is False, "migration authority drift")
    require(claims.get("release_authority") is False, "release authority drift")
    require(claims.get("authority_effect") == "NONE", "authority effect drift")

    main_source = read_text(root, "crates/heptabao-p0-server/src/main.rs")
    require_tokens(
        main_source,
        [
            "TOTAL_REQUEST_TIMEOUT",
            "MAX_CONCURRENT_CONNECTIONS",
            "MAX_CLIENT_REQUEST_IDS",
            "checked_duration_since",
            "RequestIdRegistry",
            "x-heptabao-request-id",
            "client-request-id-replayed",
            "request-read-deadline-exceeded",
            "host-listener-mismatch",
            "connection-capacity-exhausted",
            "if response.status_code == 204",
            "Content-Length: {}",
            "record_transport_rejection",
            "response-delivery-failed-after-commit",
        ],
        "P0 transport source",
    )

    durable_source = read_text(
        root,
        "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    )
    require_tokens(
        durable_source,
        [
            'require_real_directory(parent, "durable write parent directory")',
            'regular_file_status(path, "durable current generation")',
            "active_log_persist_does_not_recreate_deleted_store_root",
            "active_state_persist_does_not_recreate_deleted_store_root",
            "legacy_log_adoption_rejects_unresolved_data_temporary_file",
            "legacy_state_adoption_rejects_unresolved_data_temporary_file",
        ],
        "durable store source",
    )

    plan = read_text(root, "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md")
    authbus = read_text(root, "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md")
    audit = read_text(root, "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md")
    require_tokens(plan, ["Gate A", "Gate B", "Gate C", "Gate D", "Gate E"], "V1.3.1 plan")
    require_tokens(
        authbus,
        [
            "Client-proposed Authbus mode",
            "128 bits",
            "atomic operation claims the tuple",
            "P0 registry is deliberately weaker",
            "Blind replay",
        ],
        "Authbus request-ID contract",
    )
    require_tokens(
        audit,
        [
            "Request-attempt identity",
            "REQUEST_REJECTED",
            "RESPONSE_DELIVERY_FAILED",
            "Stable transport detail codes",
            "durable idempotency ledger",
        ],
        "P0 audit outcome contract",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
    cases = matrix.get("cases")
    require(isinstance(cases, list) and len(cases) == 10, "transport matrix must contain 10 cases")
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    require(len(case_ids) == len(set(case_ids)) == 10, "transport matrix IDs must be unique")
    require(matrix.get("qualification") is False, "transport matrix cannot self-qualify")
    require(matrix.get("compatibility_claim") is False, "transport matrix cannot claim compatibility")
    require(matrix.get("authority_effect") == "NONE", "transport matrix authority drift")

    workflow_path = ".github/workflows/plan-v1.3-gap-closure.yml"
    workflow = read_text(root, workflow_path)
    require_tokens(
        workflow,
        [
            "permissions:\n  contents: read",
            "cargo +1.98.0 fmt --all -- --check",
            "cargo +1.98.0 test --locked --workspace --all-targets",
            "cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings",
            "scripts/validate_plan_v1_3_1.py",
            "P0 transport exact-head contract PASS",
            "scripts/h02_exact_head_matrix_v1.py",
            "executed_entry_count",
            "authority-sentinel",
        ],
        "V1.3.1 workflow",
    )
    for path in [
        "crates/heptabao-authbus-contracts/**",
        "crates/heptabao-governance/**",
        "crates/heptabao-oracle-observer/**",
        "crates/heptabao-p0-server/**",
        "crates/heptabao-platform-bakeoff/**",
        "crates/heptabao-platform-contracts/**",
        "crates/heptabao-protocol/**",
        "probes/h02/openraft-tokio/**",
    ]:
        require(path in workflow, f"workflow path coverage missing: {path}")
    for forbidden in [
        "contents: write",
        "persist-credentials: true",
        "git push",
        "git commit",
        "git rebase",
    ]:
        require(forbidden not in workflow, f"write-capable workflow marker forbidden: {forbidden}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        validate(args.root)
    except (OSError, ValidationError, yaml.YAMLError) as error:
        print(f"HeptaBao V1.3.1 gap-closure validation FAILED: {error}")
        return 1
    print(
        "HeptaBao V1.3.1 gap-closure validation passed: "
        "repository remediation source-bound; exact-head and independent evidence required; "
        "qualification=false authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
