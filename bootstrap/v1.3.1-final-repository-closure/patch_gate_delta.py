#!/usr/bin/env python3
"""Close cross-platform validator and negative-gate residuals for V1.3.1."""

from __future__ import annotations

from pathlib import Path

ROOT = Path.cwd()


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, value: str) -> None:
    (ROOT / relative).write_text(value, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    value = read(relative)
    count = value.count(old)
    if count != 1:
        raise SystemExit(
            f"{relative}: expected one gate-delta replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))


def append_once(relative: str, heading: str, section: str) -> None:
    value = read(relative)
    if heading in value:
        raise SystemExit(f"{relative}: duplicate section: {heading}")
    write(relative, value.rstrip() + "\n\n" + section.strip() + "\n")


# V1.2 workflow validator must be invariant to checkout newline policy.
replace_once(
    "scripts/validate_plan_v1_2.py",
    """    if not workflow_texts:
        fail("no workflows found")
    for path, text in workflow_texts.items():
""",
    """    if not workflow_texts:
        fail("no workflows found")
    workflow_texts = {
        path: text.replace("\\r\\n", "\\n").replace("\\r", "\\n")
        for path, text in workflow_texts.items()
    }
    for path, text in workflow_texts.items():
""",
)
replace_once(
    "tests/plan/test_plan_v1_2.py",
    """    def test_lock_source_drift_fails_closed(self):
""",
    """    def test_workflow_policy_is_crlf_invariant(self):
        workflow = (
            ROOT / ".github/workflows/plan-integrity-v4.yml"
        ).read_text(encoding="utf-8").replace("\\n", "\\r\\n")
        validator.validate_workflow_policy(
            {".github/workflows/plan-integrity-v4.yml": workflow}
        )

    def test_lock_source_drift_fails_closed(self):
""",
)

# Reject any derive list containing Debug immediately above SecretBytes.
replace_once(
    "scripts/validate_plan_v1_3.py",
    """    require("#[derive(Clone, Debug, Eq, PartialEq)]\\npub struct SecretBytes" not in text, "secret Debug leaks owned bytes")
""",
    """    require(
        re.search(
            r"#\\[derive\\([^)]*\\bDebug\\b[^)]*\\)\\]\\s*pub struct SecretBytes",
            text,
        )
        is None,
        "secret Debug leaks owned bytes",
    )
""",
)
replace_once(
    "tests/plan/test_plan_v1_3.py",
    """            "#[derive(Clone, Eq, PartialEq)]\\npub struct SecretBytes",
            "#[derive(Clone, Debug, Eq, PartialEq)]\\npub struct SecretBytes",
""",
    """            "#[derive(Eq, PartialEq)]\\npub struct SecretBytes",
            "#[derive(Eq, Debug, PartialEq)]\\npub struct SecretBytes",
""",
)

# Machine state and blocker register.
replace_once(
    "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml",
    """  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension:
""",
    """  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
  workflow_policy_cross_platform_newline_normalization: IMPLEMENTED_SOURCE
  secret_debug_derive_negative_gate: IMPLEMENTED_SOURCE
blocker_extension:
""",
)
replace_once(
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
    """effective_counts:
  repository_controlled: 22
  external_or_repository_setting: 8
  total: 30
""",
    """- id: HB-BLK-REPO-023
  class: REPOSITORY_CONTROLLED
  severity: MEDIUM
  title: workflow policy validation was sensitive to CRLF checkout normalization
  owner_role: qualification-tooling
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - workflow text is normalized before semantic token and forbidden-pattern checks
  - a CRLF regression vector executes on Windows
  - exact-head Python suites pass on Linux and Windows
  evidence:
  - scripts/validate_plan_v1_2.py
  - tests/plan/test_plan_v1_2.py
  closure_receipt_required: true
- id: HB-BLK-REPO-024
  class: REPOSITORY_CONTROLLED
  severity: HIGH
  title: SecretBytes Debug-derive negative test targeted an obsolete derive shape
  owner_role: memory-secrecy-qualification
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - any derive list containing Debug immediately above SecretBytes is rejected
  - the regression mutation starts from the current non-Clone SecretBytes declaration
  - exact-head Python and Rust suites pass
  evidence:
  - scripts/validate_plan_v1_3.py
  - tests/plan/test_plan_v1_3.py
  closure_receipt_required: true
effective_counts:
  repository_controlled: 24
  external_or_repository_setting: 8
  total: 32
""",
)
replace_once(
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    """resource_bounds:
""",
    """- id: P0-TRANSPORT-020
  title: workflow policy validation is invariant to CRLF checkout normalization
  vector: exact plan-integrity workflow represented with CRLF line endings
  expected: SEMANTICALLY_IDENTICAL_TO_LF
  required_platform: windows
- id: P0-TRANSPORT-021
  title: SecretBytes Debug derive is rejected independent of derive member order
  vector: current SecretBytes derive is mutated to include Debug in a non-legacy order
  expected: FAIL_CLOSED
  expected_validator: validate_plan_v1_3
resource_bounds:
""",
)
replace_once(
    "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    """23. state-machine admission uses a non-blocking fail-closed lock path, and the dispatch-time monotonic sample is taken only after successful lock acquisition.
""",
    """23. state-machine admission uses a non-blocking fail-closed lock path, and the dispatch-time monotonic sample is taken only after successful lock acquisition;
24. workflow-policy validation normalizes CRLF and CR to LF before semantic matching, so Windows checkout policy cannot create a false validation result;
25. the SecretBytes safety gate rejects `Debug` in any derive-member order, and its negative regression mutates the current non-Clone declaration rather than an obsolete source shape.
""",
)
append_once(
    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    "## V1.3.1 qualification-tooling residual closure",
    """## V1.3.1 qualification-tooling residual closure

| Threat | Control | Residual boundary |
|---|---|---|
| Workflow policy newline confusion | validator input is normalized from CRLF/CR to LF before exact semantic checks; Windows regression executes the same policy surface | normalization does not waive any forbidden workflow pattern |
| Secret Debug gate pattern evasion | a regex rejects any derive list containing `Debug` immediately above `SecretBytes`, independent of member order; the negative test mutates the current declaration | compile-time and independent source review remain required |
""",
)

# Extend V1.3.1 semantic validator to bind the two gate repairs.
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "bounded_state_admission_and_fresh_dispatch_time",
    }
""",
    """        "bounded_state_admission_and_fresh_dispatch_time",
        "workflow_policy_cross_platform_newline_normalization",
        "secret_debug_derive_negative_gate",
    }
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        isinstance(added_blockers, list) and len(added_blockers) == 5,
        "V1.3.1 blocker extension must contain five repository blockers",
""",
    """        isinstance(added_blockers, list) and len(added_blockers) == 7,
        "V1.3.1 blocker extension must contain seven repository blockers",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "HB-BLK-REPO-022",
        },
""",
    """            "HB-BLK-REPO-022",
            "HB-BLK-REPO-023",
            "HB-BLK-REPO-024",
        },
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    state_lock_contract = read_text(
        root,
        "docs/execution/HEPTABAO_P0_STATE_LOCK_AND_DISPATCH_DEADLINE_ADDENDUM_V1.md",
    )
""",
    """    state_lock_contract = read_text(
        root,
        "docs/execution/HEPTABAO_P0_STATE_LOCK_AND_DISPATCH_DEADLINE_ADDENDUM_V1.md",
    )
    v12_validator = read_text(root, "scripts/validate_plan_v1_2.py")
    v13_validator = read_text(root, "scripts/validate_plan_v1_3.py")
    v12_tests = read_text(root, "tests/plan/test_plan_v1_2.py")
    v13_tests = read_text(root, "tests/plan/test_plan_v1_3.py")
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "state-machine admission",
        ],
""",
    """            "state-machine admission",
            "workflow-policy validation",
            "derive-member order",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "Request identity or delivery ambiguity",
        ],
""",
    """            "Request identity or delivery ambiguity",
            "Workflow policy newline confusion",
            "Secret Debug gate pattern evasion",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
    """    require_tokens(
        v12_validator,
        ['text.replace("\\\\r\\\\n", "\\\\n").replace("\\\\r", "\\\\n")'],
        "V1.2 workflow newline normalization",
    )
    require_tokens(
        v12_tests,
        ["test_workflow_policy_is_crlf_invariant", '.replace("\\\\n", "\\\\r\\\\n")'],
        "V1.2 CRLF regression",
    )
    require_tokens(
        v13_validator,
        [r"[^)]*\\bDebug\\b[^)]*", "pub struct SecretBytes"],
        "V1.3 SecretBytes Debug gate",
    )
    require_tokens(
        v13_tests,
        ["#[derive(Eq, PartialEq)]\\npub struct SecretBytes", "#[derive(Eq, Debug, PartialEq)]"],
        "V1.3 SecretBytes negative mutation",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        isinstance(cases, list) and len(cases) == 19,
        "transport matrix must contain 19 cases",
""",
    """        isinstance(cases, list) and len(cases) == 21,
        "transport matrix must contain 21 cases",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        len(case_ids) == len(set(case_ids)) == 19,
""",
    """        len(case_ids) == len(set(case_ids)) == 21,
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "P0-TRANSPORT-019",
        }.issubset(set(case_ids)),
""",
    """            "P0-TRANSPORT-019",
            "P0-TRANSPORT-020",
            "P0-TRANSPORT-021",
        }.issubset(set(case_ids)),
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "test_state_lock_is_fail_closed_and_dispatch_time_is_fresh",
        ],
""",
    """            "test_state_lock_is_fail_closed_and_dispatch_time_is_fresh",
            "test_workflow_policy_is_crlf_invariant",
            "test_secret_debug_gate_rejects_any_derive_order",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "23 repository remediations and 19 transport cases source-bound; "
""",
    """        "25 repository remediations and 21 transport cases source-bound; "
""",
)

replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    """        self.assertIn("P0-TRANSPORT-019", cases)
""",
    """        self.assertIn("P0-TRANSPORT-019", cases)
        self.assertIn("P0-TRANSPORT-020", cases)
        self.assertIn("P0-TRANSPORT-021", cases)
""",
)
replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    """

if __name__ == "__main__":
""",
    """

    def test_workflow_policy_is_crlf_invariant(self) -> None:
        source = text("scripts/validate_plan_v1_2.py")
        self.assertIn(
            'text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
            source,
        )
        tests = text("tests/plan/test_plan_v1_2.py")
        self.assertIn("test_workflow_policy_is_crlf_invariant", tests)

    def test_secret_debug_gate_rejects_any_derive_order(self) -> None:
        validator = text("scripts/validate_plan_v1_3.py")
        tests = text("tests/plan/test_plan_v1_3.py")
        self.assertIn(r"[^)]*\\bDebug\\b[^)]*", validator)
        self.assertIn("#[derive(Eq, Debug, PartialEq)]", tests)
        self.assertNotIn("#[derive(Clone, Eq, PartialEq)]\\npub struct SecretBytes", tests)


if __name__ == "__main__":
""",
)

replace_once(
    "tests/plan/test_plan_v1_3_1.py",
    """    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
""",
    """    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    "scripts/validate_plan_v1_2.py",
    "scripts/validate_plan_v1_3.py",
    "tests/plan/test_plan_v1_2.py",
    "tests/plan/test_plan_v1_3.py",
""",
)

print("cross-platform workflow and SecretBytes negative gates closed")
