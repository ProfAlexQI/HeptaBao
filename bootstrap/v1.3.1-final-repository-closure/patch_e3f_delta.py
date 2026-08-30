#!/usr/bin/env python3
"""Reconcile the e3f351 state-admission repair into the final V1.3.1 closure."""

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
            f"{relative}: expected one delta replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))


replace_once(
    "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml",
    """  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension:
""",
    """  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension:
""",
)

replace_once(
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
    """effective_counts:
  repository_controlled: 21
  external_or_repository_setting: 8
  total: 29
""",
    """- id: HB-BLK-REPO-022
  class: REPOSITORY_CONTROLLED
  severity: HIGH
  title: state-lock admission was unbounded and dispatch time was sampled before lock acquisition
  owner_role: request-pipeline-concurrency
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - state admission uses a non-blocking fail-closed lock path
  - busy and poisoned state return stable pre-dispatch errors
  - monotonic dispatch time is sampled only after successful lock acquisition
  - exact-head Rust and transport tests pass
  evidence:
  - crates/heptabao-p0-server/src/main.rs
  - docs/execution/HEPTABAO_P0_STATE_LOCK_AND_DISPATCH_DEADLINE_ADDENDUM_V1.md
  closure_receipt_required: true
effective_counts:
  repository_controlled: 22
  external_or_repository_setting: 8
  total: 30
""",
)

replace_once(
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    """resource_bounds:
""",
    """- id: P0-TRANSPORT-019
  title: state admission is bounded and dispatch time is sampled after lock acquisition
  vector: concurrent request encounters a busy or poisoned P0 state lock
  expected_status: 503
  expected_detail_codes:
  - p0-state-busy
  - p0-state-lock-unavailable
  expected_dispatch: false
  expected_time_sample: AFTER_SUCCESSFUL_LOCK_ACQUISITION
resource_bounds:
""",
)

replace_once(
    "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    """22. raw socket, filesystem and operating-system diagnostics remain server-side while clients receive only a bounded public error vocabulary.
""",
    """22. raw socket, filesystem and operating-system diagnostics remain server-side while clients receive only a bounded public error vocabulary;
23. state-machine admission uses a non-blocking fail-closed lock path, and the dispatch-time monotonic sample is taken only after successful lock acquisition.
""",
)

replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "transport_public_error_vocabulary",
    }
""",
    """        "transport_public_error_vocabulary",
        "bounded_state_admission_and_fresh_dispatch_time",
    }
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        isinstance(added_blockers, list) and len(added_blockers) == 4,
        "V1.3.1 blocker extension must contain four repository blockers",
""",
    """        isinstance(added_blockers, list) and len(added_blockers) == 5,
        "V1.3.1 blocker extension must contain five repository blockers",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "HB-BLK-REPO-021",
        },
""",
    """            "HB-BLK-REPO-021",
            "HB-BLK-REPO-022",
        },
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "public_transport_errors_never_expose_internal_diagnostics",
        ],
""",
    """            "public_transport_errors_never_expose_internal_diagnostics",
            "use std::sync::{Arc, Mutex, TryLockError};",
            "let response = match server.try_lock()",
            "Err(TryLockError::WouldBlock)",
            'detail_code: "p0-state-busy"',
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    storage_contract = read_text(
        root,
        "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md",
    )
""",
    """    storage_contract = read_text(
        root,
        "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md",
    )
    state_lock_contract = read_text(
        root,
        "docs/execution/HEPTABAO_P0_STATE_LOCK_AND_DISPATCH_DEADLINE_ADDENDUM_V1.md",
    )
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "KV LIST",
        ],
""",
    """            "KV LIST",
            "state-machine admission",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
    """    require_tokens(
        state_lock_contract,
        [
            "non-blocking server-state try-lock",
            "p0-state-busy",
            "after successful lock acquisition",
            "CommitDisposition::NotAttempted",
        ],
        "P0 state-lock and dispatch-deadline addendum",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        isinstance(cases, list) and len(cases) == 18,
        "transport matrix must contain 18 cases",
""",
    """        isinstance(cases, list) and len(cases) == 19,
        "transport matrix must contain 19 cases",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        len(case_ids) == len(set(case_ids)) == 18,
""",
    """        len(case_ids) == len(set(case_ids)) == 19,
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "P0-TRANSPORT-018",
        }.issubset(set(case_ids)),
""",
    """            "P0-TRANSPORT-018",
            "P0-TRANSPORT-019",
        }.issubset(set(case_ids)),
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "test_transport_errors_use_public_messages",
        ],
""",
    """            "test_transport_errors_use_public_messages",
            "test_state_lock_is_fail_closed_and_dispatch_time_is_fresh",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "22 repository remediations and 18 transport cases source-bound; "
""",
    """        "23 repository remediations and 19 transport cases source-bound; "
""",
)

replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    """        self.assertIn("P0-TRANSPORT-018", cases)
""",
    """        self.assertIn("P0-TRANSPORT-018", cases)
        self.assertIn("P0-TRANSPORT-019", cases)
""",
)

replace_once(
    "tests/plan/test_plan_v1_3_1.py",
    """    "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
""",
    """    "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
    "docs/execution/HEPTABAO_P0_STATE_LOCK_AND_DISPATCH_DEADLINE_ADDENDUM_V1.md",
""",
)

print("e3f351 state-admission repair reconciled into final V1.3.1 closure")
