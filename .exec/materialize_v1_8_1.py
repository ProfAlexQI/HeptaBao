#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import subprocess
import tomllib
from pathlib import Path
from typing import Any

import yaml

PLAN_ID = "HEPTABAO-PLAN-2026-09-02-V1.8.1"
CLAIMS = {
    "qualification": False,
    "compatibility_claim": False,
    "selected_candidates": [],
    "selection_effect": "NONE",
    "production_authority": False,
    "migration_authority": False,
    "release_authority": False,
    "authority_effect": "NONE",
}
REPOSITORY_BLOCKERS = [f"HB-BLK-REPO-{number:03d}" for number in range(49, 94)]
EXTERNAL_BLOCKERS = ["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{number:03d}" for number in range(1, 8)]]
V180_WORKFLOWS = [
    "HeptaBao V1.8.0 operational service",
    "HeptaBao V1.7.0 service HA plugin compatibility",
    "HeptaBao V1.6.0 runtime recovery operations",
    "HeptaBao V1.5.0 control-plane vertical slice",
    "HeptaBao V1.4.7 post-merge truth and external admission",
    "HeptaBao V1.4.6 authoritative recovery closure",
    "plan-v1.4.5-security-invariant-closure",
    "plan-v1.4.4-module-documentation",
]


def sh(root: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=root, text=True).strip()


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def dump(value: Any) -> str:
    return yaml.safe_dump(value, sort_keys=False, width=120)


def workspace_names(root: Path) -> set[str]:
    data = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
    names: set[str] = set()
    for entry in data["workspace"]["members"]:
        for path in root.glob(entry):
            cargo = path / "Cargo.toml"
            if cargo.is_file():
                names.add(tomllib.loads(cargo.read_text(encoding="utf-8"))["package"]["name"])
    return names


def receipt(baseline: str, tree: str, reviewed_head: str) -> dict[str, Any]:
    return {
        "schema": "heptabao.repository-post-merge-closure-receipt.v1",
        "plan_id": PLAN_ID,
        "repository": {"id": 1349115072, "full_name": "TrillionniumFoundation/HeptaBao"},
        "pull_request": 67,
        "reviewed_head_commit": reviewed_head,
        "merge_commit": baseline,
        "merge_tree": tree,
        "required_reviewers": ["ProfHepta", "Tomasrgbsf"],
        "required_workflow_families": V180_WORKFLOWS,
        "administrator_bypass": False,
        "closed_repository_blockers": [f"HB-BLK-REPO-{number:03d}" for number in range(86, 94)],
        "external_or_control_blockers_closed": [],
        "claims": CLAIMS,
    }


def status(baseline: str, tree: str, module_count: int) -> dict[str, Any]:
    return {
        "schema": "heptabao.v1-8-1-repository-scope-closure-status.v1",
        "plan_id": PLAN_ID,
        "revision": "1.8.1",
        "status": "REPOSITORY_SCOPE_COMPLETE_ON_REVIEWED_MERGE_EXTERNAL_FACTS_OPEN",
        "current_plan": "docs/plan/HEPTABAO_PLAN_V1_8_1_REPOSITORY_SCOPE_CLOSURE.md",
        "current_blocker_register": "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml",
        "normative_manifest": "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_1.yaml",
        "source_baseline": {"commit": baseline, "tree": tree},
        "module_count": module_count,
        "repository_blockers_closed": REPOSITORY_BLOCKERS,
        "repository_blockers_open": [],
        "external_and_control_blockers_open": EXTERNAL_BLOCKERS,
        "repository_scope_completion_conditions": [
            "this exact V1.8.1 head passes current and inherited validation",
            "the distinct GitHub prospective merge passes the same validation",
            "ProfHepta and Tomasrgbsf approve the exact final head",
            "no blocking review or unresolved review thread remains",
            "the candidate is merged through the ordinary pull-request API without administrator bypass",
        ],
        "external_completion_admission": "docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md",
        "remaining_factual_gaps": [
            "live protected integration and main rulesets with negative control evidence",
            "three independently accountable program security and storage role receipts",
            "signed legal and clean-room disposition",
            "operated private disclosure 24x7 incident and revocation drills",
            "isolated HSM or signer trust root and revocation ceremony",
            "restricted Oracle capture sanitization and role-separated transfer",
            "independent kernel or VM power-cut filesystem qualification",
            "independently controlled exact-source reproduction",
        ],
        "claims": CLAIMS,
    }


def blockers(baseline: str, tree: str) -> dict[str, Any]:
    return {
        "schema": "heptabao.blocker-register-extension.v1_8_1",
        "plan_id": PLAN_ID,
        "revision": "1.8.1",
        "status": "REPOSITORY_SCOPE_COMPLETE_ON_REVIEWED_MERGE_EXTERNAL_FAIL_CLOSED",
        "inherits": "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml",
        "source_baseline": {"commit": baseline, "tree": tree},
        "repository_blockers_closed": [
            {"id": blocker, "state": "CLOSED_REPOSITORY_SCOPE", "authority_effect": "NONE"}
            for blocker in REPOSITORY_BLOCKERS
        ],
        "repository_blockers_open": [],
        "external_and_control_blockers_open": [
            {"id": blocker, "state": "OPEN_AUTHENTIC_COMPLETION_OBJECT_REQUIRED"}
            for blocker in EXTERNAL_BLOCKERS
        ],
        "closure_interpretation": [
            "repository-scope closure means source documentation tests and CI-owned remediation are complete for the declared scope",
            "repository-scope closure does not qualify an environment provider operator legal conclusion or compatibility profile",
            "no template self-review GitHub administrator action or same-control rerun can close an external blocker",
        ],
        "claims": CLAIMS,
    }


def plan_doc(baseline: str, tree: str) -> str:
    return f'''# HeptaBao Plan V1.8.1 — Repository-Scope Closure

## Immutable baseline

This closure tranche starts from the reviewed V1.8.0 integration merge `{baseline}`, tree `{tree}`. The merge is expected to have the V1.8.0 base and reviewed candidate as its two ordered parents.

## Objective

Consolidate the complete repository-controlled blocker chain after V1.8.0:

- preserve all 42 source-bound module guides and exact module truth;
- admit the V1.8.0 post-merge receipt for `HB-BLK-REPO-086..093`;
- mark `HB-BLK-REPO-049..093` closed only in repository scope;
- leave no repository-controlled blocker open in the current register;
- retain every control/external blocker as authentic-evidence-required;
- make the completion claim conditional on exact-head and distinct prospective-merge success, two exact-head approvals, no blocking review/thread, and ordinary PR merge without administrator bypass.

## Meaning of completion

Repository-scope completion covers source code, tests, module documentation, semantic validators, hostile tests, deterministic candidate bundles and repository-owned CI. It does not assert a live ruleset, independent employment/accountability, legal advice, 24x7 operation, isolated signing custody, restricted Oracle access, destructive power-cut evidence, independently controlled reproduction, compatibility, qualification or deployment authority.

## Required gates

The V1.8.1 pull request re-runs V1.8.1 and every inherited V1.8.0 through V1.4.4 Python/hostile contract, all plan/platform/oracle tests, deterministic source bundle comparison, and Rust 1.98 formatting, locked workspace tests and strict Clippy on both the immutable head and GitHub two-parent prospective merge.

## Final rule

On ordinary reviewed merge of this exact candidate, `HB-BLK-REPO-049..093` are closed in repository scope and `repository_blockers_open=[]`. `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open until authentic completion objects satisfy the external admission protocol.
'''


def current_docs() -> str:
    return '''# HeptaBao Current Documentation

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_8_1_REPOSITORY_SCOPE_CLOSURE.md` |
| current status | `planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_1.yaml` |
| current module truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml` |
| V1.8 post-merge receipt | `planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| external completion admission | `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md` |
| current gate | `.github/workflows/plan-v1.8.1-repository-scope-closure.yml` |

## Repository implementation state

The current source contains 42 source-bound crates covering the inherited security/recovery kernel, control-plane domains, sealed runtime, recovery and lifecycle providers, strict HTTP/HA/plugin/compatibility/client contracts, and the operational service vertical slice. On reviewed ordinary merge of the exact V1.8.1 candidate, the current register has no repository-controlled blocker open and records `HB-BLK-REPO-049..093` as closed in repository scope.

## Authority boundary

Repository completion is not environmental or organizational qualification. `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open until independently verifiable real completion objects pass the external admission protocol. No source, template, administrator privilege, same-control CI rerun or self-issued receipt can manufacture those facts.

```text
qualification=false
compatibility_claim=false
selected_candidates=[]
selection_effect=NONE
production_authority=false
migration_authority=false
release_authority=false
authority_effect=NONE
```
'''


def successor_v180_validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import subprocess, tomllib
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {"heptabao-config", "heptabao-observability", "heptabao-service", "heptabao-cluster", "heptabao-agent-proxy"}
CLAIMS = {"qualification": False, "compatibility_claim": False, "selected_candidates": [], "selection_effect": "NONE", "production_authority": False, "migration_authority": False, "release_authority": False, "authority_effect": "NONE"}
def main() -> int:
    status = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml").read_text())
    blockers = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml").read_text())
    if status["claims"] != CLAIMS or blockers["claims"] != CLAIMS:
        raise SystemExit("V1.8 authority drift")
    subprocess.run(["git", "merge-base", "--is-ancestor", status["source_baseline"]["commit"], "HEAD"], cwd=ROOT, check=True)
    data = tomllib.loads((ROOT / "Cargo.toml").read_text()); names = set()
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path / "Cargo.toml").is_file(): names.add(tomllib.loads((path / "Cargo.toml").read_text())["package"]["name"])
    if not REQUIRED.issubset(names): raise SystemExit("V1.8 crate disappeared")
    receipt = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
    if receipt["closed_repository_blockers"] != [f"HB-BLK-REPO-{number:03d}" for number in range(86, 94)]: raise SystemExit("V1.8 receipt blocker mismatch")
    if receipt["external_or_control_blockers_closed"] or receipt["claims"] != CLAIMS: raise SystemExit("V1.8 receipt overclaim")
    current = (ROOT / "docs/CURRENT_DOCUMENTATION.md").read_text()
    if "HEPTABAO_PLAN_V1_8_1_REPOSITORY_SCOPE_CLOSURE.md" not in current and "HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md" not in current:
        raise SystemExit("V1.8 lineage missing")
    print("PASS inherited V1.8 operational service lineage")
    return 0
if __name__ == "__main__": raise SystemExit(main())
'''


def successor_v180_tests() -> str:
    return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
class V180SuccessorTests(unittest.TestCase):
    def test_post_merge_receipt_closes_only_v180_repository_scope(self) -> None:
        value = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
        self.assertEqual([f"HB-BLK-REPO-{number:03d}" for number in range(86, 94)], value["closed_repository_blockers"])
        self.assertEqual([], value["external_or_control_blockers_closed"])
        self.assertEqual("NONE", value["claims"]["authority_effect"])
    def test_current_module_truth_remains_42_crates(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text())
        self.assertEqual(42, value["module_count"])
if __name__ == "__main__": unittest.main()
'''


def validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import hashlib, subprocess, tomllib
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[1]
CLAIMS = {"qualification": False, "compatibility_claim": False, "selected_candidates": [], "selection_effect": "NONE", "production_authority": False, "migration_authority": False, "release_authority": False, "authority_effect": "NONE"}
REPO = [f"HB-BLK-REPO-{number:03d}" for number in range(49, 94)]
EXTERNAL = ["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{number:03d}" for number in range(1, 8)]]
def digest(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()
def main() -> int:
    status = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml").read_text())
    blockers = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml").read_text())
    receipt = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
    if status["claims"] != CLAIMS or blockers["claims"] != CLAIMS or receipt["claims"] != CLAIMS: raise SystemExit("authority drift")
    baseline = status["source_baseline"]
    if subprocess.check_output(["git", "rev-parse", f"{baseline['commit']}^{{tree}}"], cwd=ROOT, text=True).strip() != baseline["tree"]: raise SystemExit("baseline tree drift")
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline["commit"], "HEAD"], cwd=ROOT, check=True)
    parents = subprocess.check_output(["git", "rev-list", "--parents", "-n", "1", baseline["commit"]], cwd=ROOT, text=True).split()
    if len(parents) != 3: raise SystemExit("V1.8 baseline is not a two-parent merge")
    if receipt["merge_commit"] != baseline["commit"] or receipt["merge_tree"] != baseline["tree"] or receipt["reviewed_head_commit"] != parents[2]: raise SystemExit("V1.8 post-merge receipt topology mismatch")
    if status["repository_blockers_closed"] != REPO or status["repository_blockers_open"] != []: raise SystemExit("repository closure set mismatch")
    if [item["id"] for item in blockers["repository_blockers_closed"]] != REPO or blockers["repository_blockers_open"] != []: raise SystemExit("blocker register closure mismatch")
    if status["external_and_control_blockers_open"] != EXTERNAL or [item["id"] for item in blockers["external_and_control_blockers_open"]] != EXTERNAL: raise SystemExit("external blocker set mismatch")
    data = tomllib.loads((ROOT / "Cargo.toml").read_text()); names = set()
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path / "Cargo.toml").is_file(): names.add(tomllib.loads((path / "Cargo.toml").read_text())["package"]["name"])
    truth = yaml.safe_load((ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text())
    if len(names) != 42 or truth["module_count"] != 42 or {item["crate"] for item in truth["modules"]} != names: raise SystemExit("42-crate truth mismatch")
    workflow = (ROOT / ".github/workflows/plan-v1.8.1-repository-scope-closure.yml").read_text()
    if "pull_request:" not in workflow or "push:" in workflow or "prospective-merge" not in workflow: raise SystemExit("workflow admission drift")
    manifest = yaml.safe_load((ROOT / "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_1.yaml").read_text())
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or digest(path) != item["sha256"]: raise SystemExit(f"manifest mismatch: {item['path']}")
    print("PASS V1.8.1 repository-scope closure candidate")
    return 0
if __name__ == "__main__": raise SystemExit(main())
'''


def tests() -> str:
    return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT = Path(__file__).resolve().parents[2]
class V181ClosureTests(unittest.TestCase):
    def test_all_repository_blockers_closed_and_none_open(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml").read_text())
        self.assertEqual([f"HB-BLK-REPO-{number:03d}" for number in range(49, 94)], value["repository_blockers_closed"])
        self.assertEqual([], value["repository_blockers_open"])
    def test_external_blockers_are_not_relabelled_closed(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml").read_text())
        self.assertEqual(["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{number:03d}" for number in range(1, 8)]], [item["id"] for item in value["external_and_control_blockers_open"]])
        self.assertTrue(all(item["state"] == "OPEN_AUTHENTIC_COMPLETION_OBJECT_REQUIRED" for item in value["external_and_control_blockers_open"]))
        self.assertEqual("NONE", value["claims"]["authority_effect"])
    def test_completion_conditions_forbid_admin_bypass(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml").read_text())
        self.assertTrue(any("without administrator bypass" in item for item in value["repository_scope_completion_conditions"]))
if __name__ == "__main__": unittest.main()
'''


def workflow() -> str:
    return '''name: HeptaBao V1.8.1 repository scope closure

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches: [integration/v1.4.4-technical-candidate]

permissions:
  contents: read

concurrency:
  group: v1.8.1-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
  cancel-in-progress: true

jobs:
  validate:
    name: v1.8.1 / pull_request / ${{ matrix.source_kind }}
    runs-on: ubuntu-24.04
    timeout-minutes: 260
    strategy:
      fail-fast: false
      matrix:
        source_kind: [exact-head, prospective-merge]
    env:
      SOURCE_KIND: ${{ matrix.source_kind }}
      SOURCE_SHA: ${{ matrix.source_kind == 'prospective-merge' && github.sha || github.event.pull_request.head.sha }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
      BASE_SHA: ${{ github.event.pull_request.base.sha }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ env.SOURCE_SHA }}
          fetch-depth: 0
          persist-credentials: false
      - name: Bind immutable head or two-parent prospective merge
        shell: bash
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
          if [[ "$SOURCE_KIND" == prospective-merge ]]; then
            read -r merge first second extra <<<"$(git rev-list --parents -n 1 HEAD)"
            test "$merge" = "$SOURCE_SHA"; test "$first" = "$BASE_SHA"; test "$second" = "$HEAD_SHA"; test -z "${extra:-}"
          else
            test "$SOURCE_SHA" = "$HEAD_SHA"
          fi
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-plan.txt
      - name: Validate current and every inherited contract
        shell: bash
        run: |
          set -euo pipefail
          python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
          python scripts/validate_plan_v1_8_1.py
          python scripts/validate_plan_v1_8_0.py
          python scripts/validate_plan_v1_7_0.py
          python scripts/validate_plan_v1_6_0.py
          python scripts/validate_plan_v1_5_0.py
          python scripts/validate_plan_v1_4_7.py
          python scripts/validate_plan_v1_4_6.py
          python scripts/validate_plan_v1_4_5.py
          python scripts/validate_module_documentation_v1_4_4.py
          python -m unittest discover -s tests/plan -p 'test_*.py' -v
          python -m unittest discover -s tests/platform -p 'test_*.py' -v
          python -m unittest discover -s tests/oracle -p 'test_*.py' -v
          python scripts/build_release_bundle_v1_8.py --output "$RUNNER_TEMP/one.tar.gz"
          python scripts/build_release_bundle_v1_8.py --output "$RUNNER_TEMP/two.tar.gz"
          cmp "$RUNNER_TEMP/one.tar.gz" "$RUNNER_TEMP/two.tar.gz"
      - name: Install Rust 1.98
        shell: bash
        run: rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
      - name: Validate locked 42-crate workspace
        shell: bash
        run: |
          set -euo pipefail
          cargo +1.98.0 fmt --all -- --check
          cargo +1.98.0 test --locked --workspace --all-targets
          cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
'''


def materialize(root: Path) -> None:
    baseline = sh(root, "git", "rev-parse", "HEAD")
    tree = sh(root, "git", "rev-parse", "HEAD^{tree}")
    parents = sh(root, "git", "rev-list", "--parents", "-n", "1", "HEAD").split()
    if len(parents) != 3:
        raise SystemExit("current integration head must be the reviewed V1.8 two-parent merge")
    reviewed_head = parents[2]
    names = workspace_names(root)
    if len(names) != 42:
        raise SystemExit(f"expected 42 crates, found {len(names)}")

    write(root, "planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml", dump(receipt(baseline, tree, reviewed_head)))
    write(root, "planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml", dump(status(baseline, tree, len(names))))
    write(root, "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml", dump(blockers(baseline, tree)))
    write(root, "docs/plan/HEPTABAO_PLAN_V1_8_1_REPOSITORY_SCOPE_CLOSURE.md", plan_doc(baseline, tree))
    write(root, "docs/CURRENT_DOCUMENTATION.md", current_docs())
    write(root, "scripts/validate_plan_v1_8_0.py", successor_v180_validator())
    write(root, "tests/plan/test_plan_v1_8_0.py", successor_v180_tests())
    write(root, "scripts/validate_plan_v1_8_1.py", validator())
    write(root, "tests/plan/test_plan_v1_8_1.py", tests())
    write(root, ".github/workflows/plan-v1.8.1-repository-scope-closure.yml", workflow())

    normative = [
        "docs/CURRENT_DOCUMENTATION.md",
        "docs/plan/HEPTABAO_PLAN_V1_8_1_REPOSITORY_SCOPE_CLOSURE.md",
        "docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md",
        "planning/HEPTABAO_V1_8_1_REPOSITORY_SCOPE_CLOSURE_STATUS.yaml",
        "planning/HEPTABAO_BLOCKER_REGISTER_V1_8_1.yaml",
        "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml",
        "planning/evidence/repository/HEPTABAO_V1_8_0_POST_MERGE_CLOSURE_RECEIPT.yaml",
        "scripts/validate_plan_v1_8_1.py",
        ".github/workflows/plan-v1.8.1-repository-scope-closure.yml",
    ]
    manifest = {
        "schema": "heptabao.normative-document-manifest.v1_8_1",
        "plan_id": PLAN_ID,
        "revision": "1.8.1",
        "status": "REPOSITORY_SCOPE_CLOSURE_CANDIDATE_REVIEW_REQUIRED",
        "source_baseline": {"commit": baseline, "tree": tree},
        "files": [{"path": path, "sha256": sha(root / path)} for path in sorted(normative)],
        "claims": CLAIMS,
    }
    write(root, "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_1.yaml", dump(manifest))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    materialize(args.root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
