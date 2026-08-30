#!/usr/bin/env python3
"""Apply post-preflight V1.3.1 inherited-marker and semantic-token closure."""

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
            f"{relative}: expected one final-delta replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))


replace_once(
    "scripts/validate_plan_v1_2.py",
    '''    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    if "current plan: **v1.2**" not in readme and "current plan: **v1.3**" not in readme:
        fail("README.md: current plan marker is missing")
''',
    '''    readme = (ROOT / "README.md").read_text(encoding="utf-8").lower()
    current_plan_markers = (
        "current plan: **v1.2**",
        "current plan: **v1.3**",
        "current plan: **v1.3.1 repository gap closure**",
    )
    if not any(marker in readme for marker in current_plan_markers):
        fail("README.md: current plan marker is missing")
''',
)

replace_once(
    "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml",
    '''  secret_debug_derive_negative_gate: IMPLEMENTED_SOURCE
blocker_extension: planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml
''',
    '''  secret_debug_derive_negative_gate: IMPLEMENTED_SOURCE
  inherited_readme_current_plan_marker: IMPLEMENTED_SOURCE
blocker_extension: planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml
''',
)

replace_once(
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
    '''effective_counts:
  repository_controlled: 24
  external_or_repository_setting: 8
  total: 32
''',
    '''- id: HB-BLK-REPO-025
  class: REPOSITORY_CONTROLLED
  severity: MEDIUM
  title: inherited V1.2 validator rejected the exact V1.3.1 current-plan marker
  owner_role: qualification-tooling
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - inherited validation accepts only the enumerated V1.2, V1.3 and exact V1.3.1 README markers
  - arbitrary future or malformed version markers remain rejected
  - exact-head Python suites pass
  evidence:
  - scripts/validate_plan_v1_2.py
  - README.md
  closure_receipt_required: true
effective_counts:
  repository_controlled: 25
  external_or_repository_setting: 8
  total: 33
''',
)

replace_once(
    "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    '''25. the SecretBytes safety gate rejects `Debug` in any derive-member order, and its negative regression mutates the current non-Clone declaration rather than an obsolete source shape.
''',
    '''25. the SecretBytes safety gate rejects `Debug` in any derive-member order, and its negative regression mutates the current non-Clone declaration rather than an obsolete source shape;
26. the inherited V1.2 document validator accepts the exact V1.3.1 README current-plan marker while retaining an explicit allowlist that rejects arbitrary future or malformed versions.
''',
)

replace_once(
    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    '''| Secret Debug gate pattern evasion | a regex rejects any derive list containing `Debug` immediately above `SecretBytes`, independent of member order; the negative test mutates the current declaration | compile-time and independent source review remain required |
''',
    '''| Secret Debug gate pattern evasion | a regex rejects any derive list containing `Debug` immediately above `SecretBytes`, independent of member order; the negative test mutates the current declaration | compile-time and independent source review remain required |
| Inherited current-plan marker drift | the V1.2 validator accepts only enumerated historical/current markers including the exact V1.3.1 phrase | a new plan revision must deliberately extend the allowlist and regression suite |
''',
)

replace_once(
    "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
    '''The listener records an ordered transport-attempt/effective-request identity pair before handing an envelope to the state machine. Normal and failed response delivery produce explicit phases and retain the original status and commit disposition. Internal transport diagnostics are never reflected to the peer.
''',
    '''The listener records an ordered transport-attempt/effective-request identity pair before handing an envelope to the state machine. Normal and failed response delivery produce explicit phases and retain the original status and commit disposition. Internal transport diagnostics are never reflected to the peer; client-visible failures use a bounded public error vocabulary.
''',
)

replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''        "secret_debug_derive_negative_gate",
    }
''',
    '''        "secret_debug_derive_negative_gate",
        "inherited_readme_current_plan_marker",
    }
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''        isinstance(added_blockers, list) and len(added_blockers) == 7,
        "V1.3.1 blocker extension must contain seven repository blockers",
''',
    '''        isinstance(added_blockers, list) and len(added_blockers) == 8,
        "V1.3.1 blocker extension must contain eight repository blockers",
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''            "HB-BLK-REPO-024",
        },
''',
    '''            "HB-BLK-REPO-024",
            "HB-BLK-REPO-025",
        },
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''            "derive-member order",
        ],
''',
    '''            "derive-member order",
            "inherited V1.2 document validator",
        ],
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''            "Secret Debug gate pattern evasion",
        ],
''',
    '''            "Secret Debug gate pattern evasion",
            "Inherited current-plan marker drift",
        ],
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''        ['text.replace("\\r\\n", "\\n").replace("\\r", "\\n")'],
        "V1.2 workflow newline normalization",
''',
    '''        [
            'text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
            '"current plan: **v1.3.1 repository gap closure**"',
        ],
        "V1.2 workflow and current-plan normalization",
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''        ["#[derive(Eq, PartialEq)]\\npub struct SecretBytes", "#[derive(Eq, Debug, PartialEq)]"],
''',
    '''        [r"#[derive(Eq, PartialEq)]\\npub struct SecretBytes", "#[derive(Eq, Debug, PartialEq)]"],
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''            "test_secret_debug_gate_rejects_any_derive_order",
        ],
''',
    '''            "test_secret_debug_gate_rejects_any_derive_order",
            "test_inherited_validator_accepts_exact_v131_readme_marker",
        ],
''',
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    '''        "25 repository remediations and 21 transport cases source-bound; "
''',
    '''        "26 repository remediations and 21 transport cases source-bound; "
''',
)

replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    '''            'text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
''',
    '''            r'text.replace("\\r\\n", "\\n").replace("\\r", "\\n")',
''',
)
replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    '''    def test_secret_debug_gate_rejects_any_derive_order(self) -> None:
''',
    '''    def test_inherited_validator_accepts_exact_v131_readme_marker(self) -> None:
        source = text("scripts/validate_plan_v1_2.py")
        self.assertIn(
            '"current plan: **v1.3.1 repository gap closure**"', source
        )
        self.assertNotIn('"current plan: **v1.4**"', source)

    def test_secret_debug_gate_rejects_any_derive_order(self) -> None:
''',
)

print("post-preflight inherited-marker and semantic-token closure applied")
