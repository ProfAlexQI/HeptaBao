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
    require(
        status.get("schema") == "heptabao.v1-3-1-gap-closure-status.v1",
        "status schema drift",
    )
    require(status.get("revision") == "1.3.1", "status revision drift")
    integration = status.get("canonical_integration")
    require(isinstance(integration, dict), "canonical integration missing")
    require(
        integration.get("branch") == "codex/plan-v1.3-gap-closure-v2",
        "canonical branch drift",
    )
    require(integration.get("pull_request") == 45, "canonical pull request drift")
    require(
        integration.get("ordinary_reviewable_source") is True,
        "ordinary source must remain true",
    )
    require(
        integration.get("compressed_transport_is_not_canonical_delivery") is True,
        "compressed source transport cannot become canonical delivery",
    )
    require(
        integration.get("ci_workflow_authored_source_publication_forbidden") is True,
        "CI workflow source self-publication must remain forbidden",
    )
    require(
        integration.get("maintainer_invoked_git_data_tree_republish_allowed") is True,
        "tree-preserving maintainer Git Data republish contract missing",
    )
    require(
        integration.get("final_tree_preserving_republish_required") is True,
        "final tree-preserving republish requirement missing",
    )
    require(
        integration.get("source_head_and_synthetic_merge_admission_required") is True,
        "source-head and synthetic-merge dual admission required",
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
        "bounded_transport_rejection_writes",
        "absolute_total_response_write_deadline",
        "connection_worker_spawn_fail_closed",
        "strict_invalid_deadline_and_json_string_validation",
        "operation_specific_body_fail_closed",
        "owned_request_response_and_wire_buffer_hygiene",
        "owned_target_and_kv_path_hygiene",
        "authbus_binding_redaction_and_digest_preimage_hygiene",
    }
    require(set(remediation) == expected_remediation, "repository remediation coverage drift")
    require(
        all(str(value).startswith("IMPLEMENTED") for value in remediation.values()),
        "source remediation must remain explicitly implemented",
    )

    execution = status.get("execution_required")
    require(isinstance(execution, dict) and execution, "execution requirements missing")
    require(
        all(
            value in {"REQUIRED_EXACT_HEAD", "REQUIRED_EXTERNAL_IDENTITY"}
            for value in execution.values()
        ),
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
    require(
        claims.get("compatibility_claim") is False,
        "compatibility authority drift",
    )
    require(claims.get("selected_candidates") == [], "candidate selection drift")
    require(claims.get("selection_effect") == "NONE", "selection effect drift")
    require(
        claims.get("production_authority") is False,
        "production authority drift",
    )
    require(
        claims.get("migration_authority") is False,
        "migration authority drift",
    )
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
            "write_response_with_timeout",
            "fn write_response_until<W: TimedWrite>(",
            "checked_duration_since(Instant::now())",
            "stream.write(&bytes[offset..])",
            "set response flush timeout failed",
            "response write deadline exceeded",
            "thread::Builder::new()",
            "connection-worker-spawn-failed",
            "spawn_failure_active.fetch_sub",
            "record_worker_spawn_failure",
            "partial_write_progress_cannot_reset_absolute_deadline",
            "worker_spawn_failure_releases_capacity_and_is_audited",
            "operation: Option<Operation>",
            "delivery_operation",
            "clear_request_buffers",
            "buffer[..count].fill(0)",
            "bytes.fill(0)",
            "impl fmt::Debug for RequestIdRegistry",
            "request_registry_debug_redacts_live_ids",
        ],
        "P0 transport source",
    )
    require(
        "write_all(&bytes)" not in main_source,
        "per-call write_all cannot prove one absolute response deadline",
    )
    require(
        "thread::spawn(" not in main_source,
        "infallible per-connection thread spawn is forbidden",
    )
    require(
        "#[derive(Debug)]\nstruct RequestIdRegistry" not in main_source,
        "request registry must not derive identifier-bearing Debug",
    )

    protocol_source = read_text(root, "crates/heptabao-protocol/src/lib.rs")
    require_tokens(
        protocol_source,
        [
            "impl Drop for CanonicalTarget",
            "pub fn matches_canonical(&self, raw: &str) -> bool",
            "impl Drop for HeaderMap",
            "impl Drop for ParsedHttpRequest",
            "self.deadline <= self.received_at",
            "deadline_must_be_strictly_after_receipt",
            "request_debug_redacts_path_header_values_and_body",
            "canonical_target_drop_executes_zeroizing_path",
            "ZEROIZED_STRING_OBSERVATIONS",
            "value.fill(0)",
            "body_bytes",
        ],
        "protocol secret, target and deadline source",
    )
    for forbidden in [
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct HeaderMap",
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct ParsedHttpRequest",
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct RequestEnvelope",
    ]:
        require(
            forbidden not in protocol_source,
            f"secret-bearing derived surface forbidden: {forbidden}",
        )

    p0_lib_source = read_text(root, "crates/heptabao-p0-server/src/lib.rs")
    require_tokens(
        p0_lib_source,
        [
            "operation_body_is_valid(operation, &envelope.request.body)",
            '"operation-body-forbidden"',
            'Operation::SysInit => body == b"{}"',
            "struct SecretPath(String);",
            "impl Drop for SecretPath",
            "BTreeMap<SecretPath, SecretBytes>",
            "impl Drop for P0Response",
            "response.body.fill(0)",
            "parse_secret_field",
            "byte == b'\"'",
            "append_json_string_bytes",
            "invalid_unescaped_quote_is_rejected",
            "ignored_operation_bodies_fail_closed_before_dispatch",
            "body_bytes",
            "root_token.fill(0)",
            "unseal_key.fill(0)",
            "impl fmt::Debug for ServerState",
            "server_debug_redacts_kv_paths_and_values",
            "secret_path_drop_executes_zeroizing_path",
            "ZEROIZED_STRING_OBSERVATIONS",
            "kv_entries",
        ],
        "P0 body, path and secret-response source",
    )
    require(
        p0_lib_source.index(
            "operation_body_is_valid(operation, &envelope.request.body)"
        )
        < p0_lib_source.index("let request_event = AuditEvent"),
        "operation body validation must precede request acceptance audit and dispatch",
    )
    require(
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct P0Response" not in p0_lib_source,
        "P0 response must not derive secret-bearing Clone/Debug",
    )
    require(
        "#[derive(Debug)]\nstruct ServerState" not in p0_lib_source,
        "server state must not derive KV-bearing Debug",
    )

    authbus_source = read_text(root, "crates/heptabao-authbus-contracts/src/lib.rs")
    require_tokens(
        authbus_source,
        [
            "impl fmt::Debug for RequestBinding",
            "canonical_target.matches_canonical(self.canonical_target)",
            "canonical_request.fill(0)",
            "payload.fill(0)",
            "[REDACTED_SUBJECT]",
            "request_binding_debug_redacts_target_host_and_body",
            "impl fmt::Debug for InMemoryReplayCache",
        ],
        "Authbus canonical, diagnostic and provider-preimage source",
    )
    require(
        "canonical_target.canonical_string() != self.canonical_target" not in authbus_source,
        "Authbus canonical equality must not allocate a duplicate target string",
    )
    for forbidden in [
        "#[derive(Clone, Eq, PartialEq)]\npub struct AuthbusAssertion",
        "#[derive(Clone, Eq, PartialEq)]\npub struct VerifiedAuthbusIdentity",
    ]:
        require(
            forbidden not in authbus_source,
            f"Authbus implicit identity copy forbidden: {forbidden}",
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

    durable_main_source = read_text(
        root,
        "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs",
    )
    require_tokens(
        durable_main_source,
        [
            "legacy-cluster-adoption-copy",
            "legacy_artifacts_unchanged",
            "legacy_markers_created",
            "legacy_cluster_replay_matches",
            "legacy_post_adoption_restart_matches",
            "legacy_post_adoption_write_index",
            "legacy_artifact_bytes_preserved",
            "legacy_full_cluster_replay",
            "legacy_post_adoption_write_restart",
        ],
        "durable legacy-adoption execution source",
    )

    plan = read_text(
        root,
        "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    )
    authbus_lifecycle = read_text(
        root,
        "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md",
    )
    authbus_contract = read_text(
        root,
        "docs/auth/HEPTABAO_AUTHBUS_INTEGRATION_CONTRACT_V1.md",
    )
    protocol_contract = read_text(
        root,
        "docs/protocol/HEPTABAO_H03_PROTOCOL_CONTRACT_V1.md",
    )
    audit = read_text(root, "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md")
    p0_execution = read_text(
        root,
        "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
    )
    threat_model = read_text(
        root,
        "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    )
    canonical_source = read_text(
        root,
        "docs/governance/HEPTABAO_CANONICAL_SOURCE_PUBLICATION_CONTRACT_V1.md",
    )
    require_tokens(
        canonical_source,
        [
            "CI self-publication",
            "maintainer-invoked connected GitHub Git Data API commit",
            "final tree-preserving republish",
            "GitHub synthetic merge",
            "source-head success cannot substitute for synthetic-merge success",
            "not a signature, independent review, qualification receipt",
        ],
        "canonical source publication contract",
    )
    require_tokens(
        plan,
        [
            "Gate A",
            "Gate B",
            "Gate C",
            "Gate D",
            "Gate E",
            "bounded write deadline",
            "absolute response-write deadline",
            "operation-specific body validation",
            "owned canonical target",
            "connection-worker-spawn-failed",
            "digest preimage",
            "raw unescaped quotes",
            "11 runtime-observed",
            "three exact-head root-unit-gate",
            "Source-marker presence is never counted as runtime PASS",
            "legacy artifact bytes",
            "post-adoption restart",
        ],
        "V1.3.1 plan",
    )
    require_tokens(
        authbus_lifecycle,
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
        authbus_contract,
        [
            "without constructing another target string",
            "temporary canonical request byte vector is overwritten",
            "temporary unsigned assertion payload",
            "Providers must not retain",
            "diagnostic redaction",
        ],
        "Authbus integration contract",
    )
    require_tokens(
        protocol_contract,
        [
            "deadline <= received_at",
            "operation-specific",
            "Header values are stored as owned byte vectors",
            "Canonical targets own their path and query strings",
            "raw unescaped quote",
            "socket ingress also overwrites",
        ],
        "protocol contract",
    )
    require_tokens(
        audit,
        [
            "Request-attempt identity",
            "REQUEST_REJECTED",
            "RESPONSE_DELIVERY_FAILED",
            "Stable transport and request detail codes",
            "durable idempotency ledger",
            "connection-worker-spawn-failed",
            "absolute response-write deadline",
            "operation-body-forbidden",
            "exact request ID, operation and commit disposition",
            "Source-marker presence is not runtime evidence",
        ],
        "P0 audit outcome contract",
    )
    require_tokens(
        p0_execution,
        [
            "five-second absolute write lifetime",
            "operation-body-forbidden",
            "fallibly created bounded worker",
            "connection-worker-spawn-failed",
            "Owned secret-material lifetime",
            "canonical request targets",
            "in-memory KV paths",
            "rendered HTTP wire vector is overwritten",
            "in-memory server-state `Debug`",
            "unsigned signature payload vectors",
            "11 transport cases are runtime-observed",
            "Three process-internal cases",
            "EXACT_HEAD_ROOT_UNIT_GATE",
        ],
        "P0 execution contract",
    )
    require_tokens(
        threat_model,
        [
            "Operation/body confusion or ignored payload",
            "Non-reading peer extends response lifetime",
            "Secret leakage through derived Debug or Clone",
            "Secret residue in owned user-space buffers",
            "Malformed P0 JSON accepted as a secret value",
            "unsigned signature payload",
        ],
        "V1.3 threat model delta",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
    cases = matrix.get("cases")
    require(
        isinstance(cases, list) and len(cases) == 14,
        "transport matrix must contain 14 cases",
    )
    case_ids = [case.get("id") for case in cases if isinstance(case, dict)]
    require(
        len(case_ids) == len(set(case_ids)) == 14,
        "transport matrix IDs must be unique",
    )
    require(
        {
            "P0-TRANSPORT-011",
            "P0-TRANSPORT-012",
            "P0-TRANSPORT-013",
            "P0-TRANSPORT-014",
        }.issubset(set(case_ids)),
        "final transport resource/body/lifetime cases missing",
    )
    taxonomy = matrix.get("evidence_taxonomy")
    require(isinstance(taxonomy, dict), "transport evidence taxonomy missing")
    require(taxonomy.get("runtime_status") == "RUNTIME_PASS", "runtime status drift")
    require(
        taxonomy.get("root_unit_gate_status") == "UNIT_GATE_PASS",
        "root unit-gate status drift",
    )
    require(taxonomy.get("runtime_case_count") == 11, "runtime case count drift")
    require(
        taxonomy.get("root_unit_gate_case_count") == 3,
        "root unit-gate case count drift",
    )
    require(
        taxonomy.get("source_marker_only_runtime_pass_forbidden") is True,
        "source-marker-only runtime PASS must remain forbidden",
    )
    modes = {
        case.get("id"): case.get("evidence_mode")
        for case in cases
        if isinstance(case, dict)
    }
    unit_gate_ids = {
        "P0-TRANSPORT-011",
        "P0-TRANSPORT-012",
        "P0-TRANSPORT-014",
    }
    require(
        {case_id for case_id, mode in modes.items() if mode == "EXACT_HEAD_ROOT_UNIT_GATE"}
        == unit_gate_ids,
        "root unit-gate transport case classification drift",
    )
    require(
        sum(mode == "RUNTIME_OBSERVED" for mode in modes.values()) == 11,
        "runtime-observed transport case classification drift",
    )
    cases_by_id = {case["id"]: case for case in cases if isinstance(case, dict)}
    require(
        cases_by_id["P0-TRANSPORT-011"].get("required_unit_test")
        == "partial_write_progress_cannot_reset_absolute_deadline",
        "response deadline unit test binding drift",
    )
    require(
        cases_by_id["P0-TRANSPORT-012"].get("required_unit_test")
        == "worker_spawn_failure_releases_capacity_and_is_audited",
        "worker spawn unit test binding drift",
    )
    require(
        set(cases_by_id["P0-TRANSPORT-014"].get("required_unit_tests", []))
        == {
            "canonical_target_drop_executes_zeroizing_path",
            "secret_path_drop_executes_zeroizing_path",
        },
        "controlled-drop unit test binding drift",
    )
    require(
        matrix.get("resource_bounds", {}).get("response_write_deadline_mode")
        == "ABSOLUTE_REMAINING_TIME_PER_WRITE_AND_FLUSH",
        "response write deadline mode drift",
    )
    exact_requirements = matrix.get("exact_head_requirements", {})
    require(exact_requirements.get("runtime_case_count") == 11, "exact runtime count drift")
    require(
        exact_requirements.get("root_unit_gate_case_count") == 3,
        "exact root-unit count drift",
    )
    require(
        exact_requirements.get("root_unit_gate_must_bind_same_commit_and_tree") is True,
        "root unit gate source binding must remain exact",
    )
    require(
        exact_requirements.get("source_marker_only_runtime_pass_forbidden") is True,
        "exact matrix cannot count source markers as runtime PASS",
    )
    require(matrix.get("qualification") is False, "transport matrix cannot self-qualify")
    require(
        matrix.get("compatibility_claim") is False,
        "transport matrix cannot claim compatibility",
    )
    require(matrix.get("authority_effect") == "NONE", "transport matrix authority drift")

    manifest = read_yaml(
        root,
        "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3_1.yaml",
    )
    manifest_paths = {
        entry.get("path")
        for entry in manifest.get("documents", [])
        if isinstance(entry, dict)
    }
    for required_path in {
        "docs/governance/HEPTABAO_CANONICAL_SOURCE_PUBLICATION_CONTRACT_V1.md",
        "scripts/p0_transport_exact_v1.py",
        ".github/workflows/plan-v1.3.1-final-exact.yml",
        ".github/workflows/plan-v1.3.1-merge-admission.yml",
    }:
        require(required_path in manifest_paths, f"normative manifest missing: {required_path}")
    semantics = manifest.get("closure_semantics", {})
    require(
        semantics.get("source_marker_presence_is_runtime_evidence") is False,
        "manifest cannot treat source markers as runtime evidence",
    )
    require(
        semantics.get("source_head_success_is_merge_admission") is False,
        "source-head success cannot imply merge admission",
    )
    require(
        semantics.get("tree_preserving_api_republish_is_independent_review") is False,
        "tree republish cannot imply independent review",
    )

    residual_tests = read_text(root, "tests/plan/test_v1_3_1_residual_hardening.py")
    require_tokens(
        residual_tests,
        [
            "test_response_writer_uses_one_absolute_deadline",
            "test_operation_body_policy_precedes_dispatch",
            "test_sensitive_target_and_kv_path_lifetimes_are_controlled",
            "test_transport_matrix_names_the_residual_closures",
            "test_transport_matrix_separates_runtime_and_unit_gate_evidence",
            "test_durable_legacy_adoption_preserves_and_replays_full_cluster",
        ],
        "V1.3.1 residual regression tests",
    )

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
        require(
            forbidden not in workflow,
            f"write-capable workflow marker forbidden: {forbidden}",
        )

    final_workflow = read_text(root, ".github/workflows/plan-v1.3.1-final-exact.yml")
    require_tokens(
        final_workflow,
        [
            "workflow_call:",
            "source_kind:",
            "EXPECTED_HEAD_SHA",
            "EXPECTED_BASE_SHA",
            "GITHUB_SYNTHETIC_MERGE",
            "HEPTABAO_ROOT_GATE_COMMIT",
            "HEPTABAO_ROOT_GATE_TREE",
            "artifact-digest",
            "technical-execution-receipt.json",
        ],
        "V1.3.1 reusable exact-source workflow",
    )
    merge_workflow = read_text(root, ".github/workflows/plan-v1.3.1-merge-admission.yml")
    require_tokens(
        merge_workflow,
        [
            "uses: ./.github/workflows/plan-v1.3.1-final-exact.yml",
            "source_sha: ${{ github.sha }}",
            "source_kind: GITHUB_SYNTHETIC_MERGE",
            "expected_head_sha: ${{ github.event.pull_request.head.sha }}",
            "expected_base_sha: ${{ github.event.pull_request.base.sha }}",
            "permissions:\n  contents: read",
        ],
        "V1.3.1 synthetic-merge admission workflow",
    )
    for candidate in [final_workflow, merge_workflow]:
        for forbidden in [
            "contents: write",
            "persist-credentials: true",
            "git push",
            "git commit",
            "git rebase",
        ]:
            require(
                forbidden not in candidate,
                f"write-capable final workflow marker forbidden: {forbidden}",
            )



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    try:
        validate(args.root)
    except (OSError, ValidationError, yaml.YAMLError) as error:
        print(f"HeptaBao V1.3.1 gap-closure validation FAILED: {error}")
        return 1
    print(
        "HeptaBao V1.3.1 gap-closure validation passed: "
        "18 repository remediations; 11 runtime and 3 exact-head root-unit transport cases; "
        "source-head plus synthetic-merge execution and independent evidence required; "
        "qualification=false authority=NONE"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
