#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import textwrap
import tomllib
from pathlib import Path
from typing import Any

import yaml

BASELINE_COMMIT = "54d524214df443752a2ecaeff6d4a05625bf52c7"
BASELINE_TREE = "c22288f561fdd711e908ce8a70c0116601d519e5"
SOURCE_HEAD = "837668cb879683bc60808584d2ebdedd42a397aa"
SOURCE_TREE = BASELINE_TREE
BASE_COMMIT = "489a104450ff48c49e7fb61e167e566ea5e0e6c7"
REPOSITORY_ID = 1349115072
REPOSITORY_FULL_NAME = "TrillionniumFoundation/HeptaBao"
PLAN_ID = "HEPTABAO-PLAN-2026-09-02-V1.4.7"
TRUTH_PATH = Path("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml")
MANIFEST_PATH = Path("planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml")
BEGIN_API = "<!-- BEGIN GENERATED V1.4.7 PUBLIC API TRUTH; DO NOT EDIT -->"
END_API = "<!-- END GENERATED V1.4.7 PUBLIC API TRUTH -->"
BEGIN_FACTS = "<!-- BEGIN GENERATED V1.4.7 MODULE FACTS; DO NOT EDIT -->"
END_FACTS = "<!-- END GENERATED V1.4.7 MODULE FACTS -->"
BEGIN_INDEX = "<!-- BEGIN V1.4.7 MODULE TRUTH INDEX -->"
END_INDEX = "<!-- END V1.4.7 MODULE TRUTH INDEX -->"

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

PUBLIC_RE = re.compile(
    r"^\s*pub\s+(?:(async|unsafe)\s+)?(struct|enum|trait|type|const|static|fn|mod|use)\s+(.+?)\s*$"
)
TEST_ATTR_RE = re.compile(r"^\s*#\s*\[\s*(?:[A-Za-z_][A-Za-z0-9_]*::)*test(?:\s*\([^]]*\))?\s*]\s*$")
FN_RE = re.compile(r"^\s*(?:pub\s+)?(?:async\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)")
NAME_RES = {
    "struct": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "enum": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "trait": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "type": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "const": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "static": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "fn": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
    "mod": re.compile(r"([A-Za-z_][A-Za-z0-9_]*)"),
}


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def normalize_line(value: str) -> str:
    return " ".join(value.strip().split())


def strip_block_comments(lines: list[str]) -> list[str]:
    output: list[str] = []
    depth = 0
    for original in lines:
        line = original
        result: list[str] = []
        index = 0
        while index < len(line):
            if depth:
                if line.startswith("/*", index):
                    depth += 1
                    index += 2
                elif line.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
                continue
            if line.startswith("/*", index):
                depth = 1
                index += 2
                continue
            if line.startswith("//", index):
                break
            result.append(line[index])
            index += 1
        output.append("".join(result))
    return output


def public_items(path: Path, root: Path) -> list[dict[str, Any]]:
    original = path.read_text(encoding="utf-8").splitlines()
    cleaned = strip_block_comments(original)
    items: list[dict[str, Any]] = []
    for number, line in enumerate(cleaned, 1):
        match = PUBLIC_RE.match(line)
        if not match:
            continue
        modifier, kind, tail = match.groups()
        if kind == "use":
            name = normalize_line(tail.rstrip(";"))
        else:
            name_match = NAME_RES[kind].match(tail)
            if not name_match:
                continue
            name = name_match.group(1)
        items.append(
            {
                "kind": kind,
                "name": name,
                "modifier": modifier or None,
                "path": path.relative_to(root).as_posix(),
                "line": number,
                "signature": normalize_line(original[number - 1]),
            }
        )
    return items


def test_functions(path: Path, root: Path) -> list[dict[str, Any]]:
    original = path.read_text(encoding="utf-8").splitlines()
    cleaned = strip_block_comments(original)
    pending = False
    tests: list[dict[str, Any]] = []
    for number, line in enumerate(cleaned, 1):
        if TEST_ATTR_RE.match(line):
            pending = True
            continue
        if pending:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            match = FN_RE.match(line)
            if match:
                tests.append(
                    {
                        "name": match.group(1),
                        "path": path.relative_to(root).as_posix(),
                        "line": number,
                    }
                )
            pending = False
    return tests


def dependency_sections(data: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    sections: list[tuple[str, dict[str, Any]]] = []
    for key in ("dependencies", "dev-dependencies", "build-dependencies"):
        value = data.get(key)
        if isinstance(value, dict):
            sections.append((key, value))
    targets = data.get("target", {})
    if isinstance(targets, dict):
        for target_name, target_data in sorted(targets.items()):
            if not isinstance(target_data, dict):
                continue
            for key in ("dependencies", "dev-dependencies", "build-dependencies"):
                value = target_data.get(key)
                if isinstance(value, dict):
                    sections.append((f"target.{target_name}.{key}", value))
    return sections


def workspace_members(root: Path) -> list[Path]:
    data = tomllib.loads((root / "Cargo.toml").read_text(encoding="utf-8"))
    raw = data.get("workspace", {}).get("members", [])
    members: list[Path] = []
    for entry in raw:
        if any(char in entry for char in "*?["):
            members.extend(path for path in root.glob(entry) if (path / "Cargo.toml").is_file())
        else:
            path = root / entry
            if (path / "Cargo.toml").is_file():
                members.append(path)
    return sorted(set(members), key=lambda item: item.as_posix())


def build_truth(root: Path) -> dict[str, Any]:
    members = workspace_members(root)
    crate_names: dict[Path, str] = {}
    for member in members:
        data = tomllib.loads((member / "Cargo.toml").read_text(encoding="utf-8"))
        crate_names[member] = data["package"]["name"]
    workspace_names = set(crate_names.values())
    modules: list[dict[str, Any]] = []
    for member in members:
        cargo_path = member / "Cargo.toml"
        cargo_data = tomllib.loads(cargo_path.read_text(encoding="utf-8"))
        crate_name = crate_names[member]
        rust_files = sorted(
            [path for path in member.rglob("*.rs") if "target" not in path.parts],
            key=lambda item: item.as_posix(),
        )
        internal_dependencies: list[dict[str, str]] = []
        for section, dependencies in dependency_sections(cargo_data):
            for dependency_name in sorted(dependencies):
                dependency_value = dependencies[dependency_name]
                package_name = dependency_name
                if isinstance(dependency_value, dict) and isinstance(dependency_value.get("package"), str):
                    package_name = dependency_value["package"]
                if package_name in workspace_names:
                    internal_dependencies.append({"name": package_name, "section": section})
        items: list[dict[str, Any]] = []
        tests: list[dict[str, Any]] = []
        for rust_file in rust_files:
            items.extend(public_items(rust_file, root))
            tests.extend(test_functions(rust_file, root))
        doc_path = Path("docs/modules") / f"{crate_name}.md"
        if not (root / doc_path).is_file():
            raise SystemExit(f"missing module guide: {doc_path}")
        modules.append(
            {
                "crate": crate_name,
                "crate_path": member.relative_to(root).as_posix(),
                "cargo_toml_sha256": sha256_file(cargo_path),
                "source_files": [
                    {"path": path.relative_to(root).as_posix(), "sha256": sha256_file(path)}
                    for path in rust_files
                ],
                "module_guide": doc_path.as_posix(),
                "internal_dependencies": sorted(
                    internal_dependencies, key=lambda item: (item["name"], item["section"])
                ),
                "public_items": sorted(
                    items, key=lambda item: (item["path"], item["line"], item["kind"], item["name"])
                ),
                "test_functions": sorted(tests, key=lambda item: (item["path"], item["line"], item["name"])),
            }
        )
    return {
        "schema": "heptabao.module-source-truth.v1",
        "plan_id": PLAN_ID,
        "baseline_commit": BASELINE_COMMIT,
        "baseline_tree": BASELINE_TREE,
        "parser": {
            "class": "bounded-lexical-rust-public-surface-v1",
            "captures": ["pub declarations", "workspace-internal dependency declarations", "test functions", "source digests"],
            "does_not_claim": ["rust name resolution", "semantic API compatibility", "production qualification"],
        },
        "module_count": len(modules),
        "modules": modules,
        "claims": CLAIMS,
    }


def dump_yaml(value: Any) -> str:
    return yaml.safe_dump(value, sort_keys=False, allow_unicode=True, width=120)


def replace_marked(text: str, begin: str, end: str, replacement: str) -> str:
    if begin in text and end in text:
        start = text.index(begin)
        finish = text.index(end, start) + len(end)
        return text[:start] + replacement + text[finish:]
    suffix = "" if text.endswith("\n") else "\n"
    return text + suffix + "\n" + replacement + "\n"


def replace_public_api_section(text: str, body: str) -> str:
    lines = text.splitlines()
    index = next((i for i, line in enumerate(lines) if line.startswith("## ") and "public api" in line.lower()), None)
    block = body.splitlines()
    if index is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend(["## Public API", "", *block])
        return "\n".join(lines).rstrip() + "\n"
    finish = index + 1
    while finish < len(lines) and not lines[finish].startswith("## "):
        finish += 1
    replacement = [lines[index], "", *block, ""]
    return "\n".join(lines[:index] + replacement + lines[finish:]).rstrip() + "\n"


def module_doc_expected(root: Path, module: dict[str, Any]) -> str:
    path = root / module["module_guide"]
    text = path.read_text(encoding="utf-8")
    api_lines = [BEGIN_API]
    api_lines.append(
        f"Source-bound lexical inventory: `{module['crate_path']}`; Cargo SHA-256 `{module['cargo_toml_sha256']}`."
    )
    api_lines.append("")
    api_lines.append("| Kind | Name | Source | Declaration |")
    api_lines.append("|---|---|---|---|")
    if module["public_items"]:
        for item in module["public_items"]:
            signature = item["signature"].replace("|", "\\|").replace("`", "\\`")
            name = item["name"].replace("|", "\\|").replace("`", "\\`")
            api_lines.append(
                f"| `{item['kind']}` | `{name}` | `{item['path']}:{item['line']}` | `{signature}` |"
            )
    else:
        api_lines.append("| — | — | — | No externally public lexical declaration was found. |")
    api_lines.append("")
    api_lines.append(
        "This table is generated from the exact candidate source. It is a bounded lexical inventory, not a stability or compatibility promise."
    )
    api_lines.append(END_API)
    text = replace_public_api_section(text, "\n".join(api_lines))
    dependencies = ", ".join(
        f"`{item['name']}` ({item['section']})" for item in module["internal_dependencies"]
    ) or "none"
    facts_lines = [
        BEGIN_FACTS,
        f"- Crate: `{module['crate']}`",
        f"- Crate path: `{module['crate_path']}`",
        f"- Cargo manifest SHA-256: `{module['cargo_toml_sha256']}`",
        f"- Rust source files: `{len(module['source_files'])}`",
        f"- Public lexical declarations: `{len(module['public_items'])}`",
        f"- Discovered test functions: `{len(module['test_functions'])}`",
        f"- Workspace-internal dependencies: {dependencies}",
        f"- Authoritative inventory: `{TRUTH_PATH.as_posix()}`",
        "- Regeneration: `python scripts/render_plan_v1_4_7.py --write`",
        "- Verification: `python scripts/render_plan_v1_4_7.py --check`",
        END_FACTS,
    ]
    facts_block = "\n".join(facts_lines)
    if BEGIN_FACTS in text and END_FACTS in text:
        text = replace_marked(text, BEGIN_FACTS, END_FACTS, facts_block)
    else:
        text = text.rstrip() + "\n\n## Machine-verified source truth\n\n" + facts_block + "\n"
    return text.rstrip() + "\n"


def module_index_expected(root: Path, truth: dict[str, Any]) -> str:
    path = root / "docs/modules/README.md"
    text = path.read_text(encoding="utf-8")
    lines = [
        BEGIN_INDEX,
        "## V1.4.7 machine-verified module truth",
        "",
        f"All `{truth['module_count']}` Cargo workspace crates are bound to source hashes, internal dependency declarations,",
        "public lexical declarations and discovered tests in",
        f"`{TRUTH_PATH.as_posix()}`. The generated Public API tables inside each module guide are normative for",
        "the exact candidate source; narrative stability or compatibility claims remain prohibited.",
        "",
        "Validation commands:",
        "",
        "```text",
        "python scripts/render_plan_v1_4_7.py --check",
        "python scripts/validate_plan_v1_4_7.py",
        "```",
        END_INDEX,
    ]
    return replace_marked(text, BEGIN_INDEX, END_INDEX, "\n".join(lines)).rstrip() + "\n"


def external_schema() -> dict[str, Any]:
    return json.loads('{\n  "$id": "https://heptabao.invalid/schemas/heptabao_external_completion_evidence_v1.schema.json",\n  "$schema": "https://json-schema.org/draft/2020-12/schema",\n  "additionalProperties": false,\n  "properties": {\n    "actors": {\n      "items": {\n        "additionalProperties": false,\n        "properties": {\n          "conflicts": {\n            "items": {\n              "type": "string"\n            },\n            "type": "array"\n          },\n          "credential_id": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "credential_issuer": {\n            "minLength": 2,\n            "type": "string"\n          },\n          "credential_not_after": {\n            "format": "date-time",\n            "type": "string"\n          },\n          "credential_not_before": {\n            "format": "date-time",\n            "type": "string"\n          },\n          "independent": {\n            "type": "boolean"\n          },\n          "organization": {\n            "minLength": 2,\n            "type": "string"\n          },\n          "revocation_authority": {\n            "minLength": 2,\n            "type": "string"\n          },\n          "role": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "stable_id": {\n            "minLength": 3,\n            "type": "string"\n          }\n        },\n        "required": [\n          "stable_id",\n          "role",\n          "organization",\n          "independent",\n          "conflicts",\n          "credential_id",\n          "credential_issuer",\n          "credential_not_before",\n          "credential_not_after",\n          "revocation_authority"\n        ],\n        "type": "object"\n      },\n      "type": "array"\n    },\n    "artifacts": {\n      "items": {\n        "additionalProperties": false,\n        "properties": {\n          "classification": {\n            "enum": [\n              "PUBLIC",\n              "SANITIZED",\n              "RESTRICTED_REFERENCE"\n            ]\n          },\n          "custody_uri": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "digest": {\n            "pattern": "^sha256:[0-9a-f]{64}$",\n            "type": "string"\n          },\n          "kind": {\n            "enum": [\n              "CEREMONY_TRANSCRIPT",\n              "CRASH_MATRIX",\n              "CROSS_ENVIRONMENT_COMPARISON",\n              "DRILL_BUNDLE",\n              "INDEPENDENCE_ATTESTATION",\n              "INDEPENDENT_REVIEW",\n              "LAB_ENVIRONMENT_ATTESTATION",\n              "LEGAL_DISPOSITION",\n              "LIVE_API_READBACK",\n              "NEGATIVE_TEST_BUNDLE",\n              "RAW_EVIDENCE_MANIFEST",\n              "READINESS_ATTESTATION",\n              "REPRODUCTION_BUNDLE",\n              "RESTRICTED_CAPTURE_REFERENCE",\n              "REVIEWED_INPUT_MANIFEST",\n              "REVOCATION_DRILL",\n              "ROLE_REGISTRY",\n              "SANITIZATION_REPORT",\n              "SANITIZED_FIXTURE",\n              "SCOPED_REVIEW_RECEIPTS",\n              "SIGNATURE_VERIFICATION",\n              "SIGNING_PROFILE",\n              "TRANSFER_COMPLETION",\n              "TRANSPARENCY_CHECKPOINT"\n            ]\n          },\n          "name": {\n            "minLength": 1,\n            "type": "string"\n          }\n        },\n        "required": [\n          "kind",\n          "name",\n          "digest",\n          "custody_uri",\n          "classification"\n        ],\n        "type": "object"\n      },\n      "type": "array"\n    },\n    "blocker_id": {\n      "enum": [\n        "HB-BLK-CTRL-001",\n        "HB-BLK-EXT-001",\n        "HB-BLK-EXT-002",\n        "HB-BLK-EXT-003",\n        "HB-BLK-EXT-004",\n        "HB-BLK-EXT-005",\n        "HB-BLK-EXT-006",\n        "HB-BLK-EXT-007"\n      ]\n    },\n    "checks": {\n      "items": {\n        "additionalProperties": false,\n        "properties": {\n          "case_id": {\n            "minLength": 1,\n            "type": "string"\n          },\n          "evidence_digest": {\n            "anyOf": [\n              {\n                "pattern": "^sha256:[0-9a-f]{64}$",\n                "type": "string"\n              },\n              {\n                "type": "null"\n              }\n            ]\n          },\n          "status": {\n            "enum": [\n              "PASS",\n              "FAIL",\n              "BLOCKED",\n              "UNKNOWN",\n              "UNEXECUTED"\n            ]\n          }\n        },\n        "required": [\n          "case_id",\n          "status",\n          "evidence_digest"\n        ],\n        "type": "object"\n      },\n      "type": "array"\n    },\n    "claims": {\n      "additionalProperties": false,\n      "properties": {\n        "authority_effect": {\n          "const": "NONE"\n        },\n        "compatibility_claim": {\n          "const": false\n        },\n        "migration_authority": {\n          "const": false\n        },\n        "production_authority": {\n          "const": false\n        },\n        "qualification": {\n          "const": false\n        },\n        "release_authority": {\n          "const": false\n        },\n        "selected_candidates": {\n          "const": []\n        },\n        "selection_effect": {\n          "const": "NONE"\n        }\n      },\n      "required": [\n        "qualification",\n        "compatibility_claim",\n        "selected_candidates",\n        "selection_effect",\n        "production_authority",\n        "migration_authority",\n        "release_authority",\n        "authority_effect"\n      ],\n      "type": "object"\n    },\n    "findings": {\n      "items": {\n        "additionalProperties": false,\n        "properties": {\n          "id": {\n            "minLength": 1,\n            "type": "string"\n          },\n          "severity": {\n            "enum": [\n              "CRITICAL",\n              "HIGH",\n              "MEDIUM",\n              "LOW",\n              "INFORMATIONAL",\n              "UNCLASSIFIED"\n            ]\n          },\n          "state": {\n            "enum": [\n              "OPEN",\n              "CLOSED",\n              "ACCEPTED_RISK"\n            ]\n          }\n        },\n        "required": [\n          "id",\n          "severity",\n          "state"\n        ],\n        "type": "object"\n      },\n      "type": "array"\n    },\n    "repository": {\n      "additionalProperties": false,\n      "properties": {\n        "full_name": {\n          "const": "TrillionniumFoundation/HeptaBao"\n        },\n        "id": {\n          "const": 1349115072\n        }\n      },\n      "required": [\n        "id",\n        "full_name"\n      ],\n      "type": "object"\n    },\n    "schema": {\n      "const": "heptabao.external-completion-evidence.v1"\n    },\n    "scope": {\n      "items": {\n        "minLength": 1,\n        "type": "string"\n      },\n      "type": "array"\n    },\n    "separation": {\n      "additionalProperties": {\n        "minLength": 2,\n        "type": "string"\n      },\n      "type": "object"\n    },\n    "signatures": {\n      "items": {\n        "additionalProperties": false,\n        "properties": {\n          "algorithm": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "expires_at": {\n            "format": "date-time",\n            "type": "string"\n          },\n          "key_id": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "payload_digest": {\n            "pattern": "^sha256:[0-9a-f]{64}$",\n            "type": "string"\n          },\n          "revocation_evidence_digest": {\n            "pattern": "^sha256:[0-9a-f]{64}$",\n            "type": "string"\n          },\n          "role": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "signature": {\n            "minLength": 16,\n            "type": "string"\n          },\n          "signed_at": {\n            "format": "date-time",\n            "type": "string"\n          },\n          "signer_id": {\n            "minLength": 3,\n            "type": "string"\n          },\n          "transparency_checkpoint_digest": {\n            "pattern": "^sha256:[0-9a-f]{64}$",\n            "type": "string"\n          },\n          "trust_root_id": {\n            "minLength": 3,\n            "type": "string"\n          }\n        },\n        "required": [\n          "signer_id",\n          "role",\n          "key_id",\n          "algorithm",\n          "signed_at",\n          "expires_at",\n          "trust_root_id",\n          "transparency_checkpoint_digest",\n          "revocation_evidence_digest",\n          "payload_digest",\n          "signature"\n        ],\n        "type": "object"\n      },\n      "type": "array"\n    },\n    "source": {\n      "additionalProperties": false,\n      "properties": {\n        "base_commit": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "commit": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "manifest_digest": {\n          "anyOf": [\n            {\n              "pattern": "^sha256:[0-9a-f]{64}$",\n              "type": "string"\n            },\n            {\n              "type": "null"\n            }\n          ]\n        },\n        "merge_commit": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "merge_parent_one": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "merge_parent_two": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "merge_tree": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        },\n        "plan_digest": {\n          "anyOf": [\n            {\n              "pattern": "^sha256:[0-9a-f]{64}$",\n              "type": "string"\n            },\n            {\n              "type": "null"\n            }\n          ]\n        },\n        "tree": {\n          "pattern": "^[0-9a-f]{40}$",\n          "type": [\n            "string",\n            "null"\n          ]\n        }\n      },\n      "required": [\n        "commit",\n        "tree",\n        "base_commit",\n        "merge_commit",\n        "merge_tree",\n        "merge_parent_one",\n        "merge_parent_two",\n        "plan_digest",\n        "manifest_digest"\n      ],\n      "type": "object"\n    },\n    "state": {\n      "enum": [\n        "UNEXECUTED",\n        "EXECUTED_PENDING_REVIEW",\n        "ACCEPTED",\n        "REJECTED",\n        "REVOKED"\n      ]\n    }\n  },\n  "required": [\n    "schema",\n    "blocker_id",\n    "state",\n    "repository",\n    "source",\n    "scope",\n    "actors",\n    "separation",\n    "checks",\n    "artifacts",\n    "findings",\n    "signatures",\n    "claims"\n  ],\n  "title": "HeptaBao external completion evidence envelope v1",\n  "type": "object"\n}\n')

def external_validator_source() -> str:
    return '#!/usr/bin/env python3\nfrom __future__ import annotations\n\nimport argparse\nimport base64\nimport copy\nimport hashlib\nimport json\nimport re\nimport subprocess\nfrom collections.abc import Callable, Sequence\nfrom datetime import datetime, timezone\nfrom pathlib import Path\nfrom typing import Any\n\nfrom jsonschema import Draft202012Validator, FormatChecker\n\nREPOSITORY_ID = 1349115072\nREPOSITORY_FULL_NAME = "TrillionniumFoundation/HeptaBao"\nSCHEMA_NAME = "heptabao.external-completion-evidence.v1"\nDOMAIN = b"HEPTABAO_EXTERNAL_COMPLETION_EVIDENCE_V1\\x00"\nROOT = Path(__file__).resolve().parents[1]\nSCHEMA_PATH = ROOT / "schemas/heptabao_external_completion_evidence_v1.schema.json"\nALLOWED_BLOCKERS = {"HB-BLK-CTRL-001", *{f"HB-BLK-EXT-{i:03d}" for i in range(1, 8)}}\nREQUIRED_ROLES = {\n    "HB-BLK-CTRL-001": {"repository_administrator", "independent_control_reviewer"},\n    "HB-BLK-EXT-001": {"program_reviewer", "security_reviewer", "storage_reviewer"},\n    "HB-BLK-EXT-002": {"legal_signer", "independent_program_reviewer"},\n    "HB-BLK-EXT-003": {"security_operations", "backup_incident_commander", "independent_observer"},\n    "HB-BLK-EXT-004": {"root_key_custodian", "crypto_reviewer", "independent_observer"},\n    "HB-BLK-EXT-005": {"oracle_operator", "sanitization_operator", "transfer_custodian", "compatibility_reviewer"},\n    "HB-BLK-EXT-006": {"storage_lab_operator", "storage_reviewer"},\n    "HB-BLK-EXT-007": {"independent_reproduction_operator", "independent_reproduction_reviewer"},\n}\nINDEPENDENT_ROLES = {\n    "independent_control_reviewer", "program_reviewer", "security_reviewer", "storage_reviewer",\n    "legal_signer", "independent_program_reviewer", "independent_observer", "crypto_reviewer",\n    "oracle_operator", "sanitization_operator", "transfer_custodian", "compatibility_reviewer",\n    "storage_lab_operator", "independent_reproduction_operator", "independent_reproduction_reviewer",\n}\nREQUIRED_CASES = {\n    "HB-BLK-CTRL-001": {\n        "live-api-readback", "failing-head-check-blocked", "missing-arbitration-blocked",\n        "stale-approval-dismissed", "non-codeowner-rejected", "force-push-rejected",\n        "branch-delete-rejected", "admin-bypass-rejected", "lookalike-context-rejected",\n    },\n    "HB-BLK-EXT-001": {\n        "program-review", "security-review", "storage-review", "identity-separation",\n        "signature-validation", "revocation-check",\n    },\n    "HB-BLK-EXT-002": {\n        "outbound-license", "contributor-policy", "mpl-interop", "third-party-materials",\n        "clean-room", "trademark", "patent", "export-crypto", "source-offer",\n        "retention-destruction", "signer-authority", "exact-source-binding",\n    },\n    "HB-BLK-EXT-003": {\n        "private-intake", "primary-coverage", "backup-coverage", "root-material-tabletop",\n        "policy-bypass-tabletop", "data-loss-tabletop", "split-brain-tabletop",\n        "supply-chain-tabletop", "signer-compromise-tabletop", "oracle-exposure-tabletop",\n        "freeze-drill", "revocation-propagation", "independent-observation",\n    },\n    "HB-BLK-EXT-004": {\n        "profile-approval", "root-key-ceremony", "delegated-key-ceremony",\n        "offline-trust-root-verification", "transparency-inclusion", "normal-rotation",\n        "delegated-compromise", "root-compromise", "consumer-revocation", "independent-observation",\n    },\n    "HB-BLK-EXT-005": {\n        "acl-role-separation", "oracle-profile-freeze", "uninitialized-health", "sealed-health",\n        "seal-status", "canonicalization-errors", "malformed-request", "side-effect-observation",\n        "deterministic-sanitization", "secret-scan", "semantic-review", "signed-transfer",\n        "implementation-receipt",\n    },\n    "HB-BLK-EXT-006": {\n        "environment-attestation", "power-cut-controller-proof", "durability-boundary-matrix",\n        "acknowledged-write-preservation", "corruption-rejection", "empty-init-forbidden",\n        "recovery-idempotence", "rpo-rto", "negative-missing-fsync", "independent-storage-review",\n    },\n    "HB-BLK-EXT-007": {\n        "environment-independence", "source-identity", "dependency-checksums", "build-from-source",\n        "exact-head-matrix", "prospective-merge-matrix", "artifact-comparison",\n        "normalizer-control", "divergence-closure", "independence-review",\n    },\n}\nREQUIRED_ARTIFACT_KINDS = {\n    "HB-BLK-CTRL-001": {"LIVE_API_READBACK", "NEGATIVE_TEST_BUNDLE", "INDEPENDENT_REVIEW"},\n    "HB-BLK-EXT-001": {"ROLE_REGISTRY", "SCOPED_REVIEW_RECEIPTS", "SIGNATURE_VERIFICATION"},\n    "HB-BLK-EXT-002": {"LEGAL_DISPOSITION", "REVIEWED_INPUT_MANIFEST", "SIGNATURE_VERIFICATION"},\n    "HB-BLK-EXT-003": {"READINESS_ATTESTATION", "DRILL_BUNDLE", "INDEPENDENT_REVIEW"},\n    "HB-BLK-EXT-004": {\n        "SIGNING_PROFILE", "CEREMONY_TRANSCRIPT", "TRANSPARENCY_CHECKPOINT",\n        "REVOCATION_DRILL", "INDEPENDENT_REVIEW",\n    },\n    "HB-BLK-EXT-005": {\n        "RESTRICTED_CAPTURE_REFERENCE", "SANITIZATION_REPORT", "SANITIZED_FIXTURE", "TRANSFER_COMPLETION",\n    },\n    "HB-BLK-EXT-006": {\n        "LAB_ENVIRONMENT_ATTESTATION", "CRASH_MATRIX", "RAW_EVIDENCE_MANIFEST", "INDEPENDENT_REVIEW",\n    },\n    "HB-BLK-EXT-007": {\n        "INDEPENDENCE_ATTESTATION", "REPRODUCTION_BUNDLE", "CROSS_ENVIRONMENT_COMPARISON", "INDEPENDENT_REVIEW",\n    },\n}\nSEPARATION_KEYS = {\n    "HB-BLK-CTRL-001": {"repository_admin_control", "independent_review_control"},\n    "HB-BLK-EXT-001": {"author_control", "program_review_control", "security_review_control", "storage_review_control"},\n    "HB-BLK-EXT-002": {"implementation_control", "legal_control", "program_review_control"},\n    "HB-BLK-EXT-003": {"primary_oncall_control", "backup_oncall_control", "observer_control", "evidence_custody"},\n    "HB-BLK-EXT-004": {"root_custody", "delegated_custody", "observer_custody", "transparency_custody"},\n    "HB-BLK-EXT-005": {"raw_capture_acl", "implementation_acl", "sanitizer_control", "transfer_custody", "signing_root"},\n    "HB-BLK-EXT-006": {\n        "primary_runner_admin", "lab_runner_admin", "primary_artifact_custody", "lab_artifact_custody",\n        "primary_signing_root", "lab_signing_root", "power_cut_control",\n    },\n    "HB-BLK-EXT-007": {\n        "primary_credential_root", "reproduction_credential_root", "primary_runner_admin", "reproduction_runner_admin",\n        "primary_cache_admin", "reproduction_cache_admin", "primary_artifact_custody", "reproduction_artifact_custody",\n        "primary_signing_root", "reproduction_signing_root", "primary_network_egress", "reproduction_network_egress",\n    },\n}\nUNEQUAL_SEPARATION_PAIRS = {\n    "HB-BLK-CTRL-001": [("repository_admin_control", "independent_review_control")],\n    "HB-BLK-EXT-001": [\n        ("author_control", "program_review_control"), ("author_control", "security_review_control"),\n        ("author_control", "storage_review_control"), ("program_review_control", "security_review_control"),\n        ("program_review_control", "storage_review_control"), ("security_review_control", "storage_review_control"),\n    ],\n    "HB-BLK-EXT-002": [\n        ("implementation_control", "legal_control"), ("implementation_control", "program_review_control"),\n        ("legal_control", "program_review_control"),\n    ],\n    "HB-BLK-EXT-003": [\n        ("primary_oncall_control", "backup_oncall_control"), ("primary_oncall_control", "observer_control"),\n        ("backup_oncall_control", "observer_control"),\n    ],\n    "HB-BLK-EXT-004": [\n        ("root_custody", "delegated_custody"), ("root_custody", "observer_custody"),\n        ("root_custody", "transparency_custody"), ("delegated_custody", "observer_custody"),\n        ("delegated_custody", "transparency_custody"), ("observer_custody", "transparency_custody"),\n    ],\n    "HB-BLK-EXT-005": [\n        ("raw_capture_acl", "implementation_acl"), ("raw_capture_acl", "sanitizer_control"),\n        ("implementation_acl", "transfer_custody"), ("sanitizer_control", "transfer_custody"),\n    ],\n    "HB-BLK-EXT-006": [\n        ("primary_runner_admin", "lab_runner_admin"),\n        ("primary_artifact_custody", "lab_artifact_custody"),\n        ("primary_signing_root", "lab_signing_root"),\n    ],\n    "HB-BLK-EXT-007": [\n        ("primary_credential_root", "reproduction_credential_root"),\n        ("primary_runner_admin", "reproduction_runner_admin"),\n        ("primary_cache_admin", "reproduction_cache_admin"),\n        ("primary_artifact_custody", "reproduction_artifact_custody"),\n        ("primary_signing_root", "reproduction_signing_root"),\n        ("primary_network_egress", "reproduction_network_egress"),\n    ],\n}\nHEX40 = re.compile(r"^[0-9a-f]{40}$")\nDIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")\nPLACEHOLDERS = {"todo", "tbd", "unknown", "unexecuted", "placeholder", "example", "none", "n/a"}\nSIGNATURE_METADATA_FIELDS = (\n    "signer_id", "role", "key_id", "algorithm", "signed_at", "expires_at", "trust_root_id",\n    "transparency_checkpoint_digest", "revocation_evidence_digest",\n)\nSignatureVerifier = Callable[[dict[str, Any], dict[str, Any], bytes], bool]\n\n\ndef fail(message: str) -> None:\n    raise ValueError(message)\n\n\ndef non_placeholder(value: Any, field: str) -> str:\n    if not isinstance(value, str) or len(value.strip()) < 2:\n        fail(f"{field}: missing")\n    lowered = value.strip().lower()\n    if lowered in PLACEHOLDERS or any(token in lowered for token in ("<", ">", "replace-me")):\n        fail(f"{field}: placeholder")\n    return value.strip()\n\n\ndef parse_time(value: Any, field: str) -> datetime:\n    if not isinstance(value, str):\n        fail(f"{field}: string date-time required")\n    try:\n        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))\n    except ValueError as error:\n        fail(f"{field}: invalid date-time: {error}")\n    if parsed.tzinfo is None:\n        fail(f"{field}: timezone required")\n    return parsed.astimezone(timezone.utc)\n\n\ndef schema_validator() -> Draft202012Validator:\n    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))\n    Draft202012Validator.check_schema(schema)\n    return Draft202012Validator(schema, format_checker=FormatChecker())\n\n\ndef validate_schema(data: dict[str, Any]) -> None:\n    errors = sorted(schema_validator().iter_errors(data), key=lambda item: list(item.absolute_path))\n    if errors:\n        error = errors[0]\n        location = ".".join(str(item) for item in error.absolute_path) or "$"\n        fail(f"schema validation failed at {location}: {error.message}")\n\n\ndef signing_payload(data: dict[str, Any], signature: dict[str, Any]) -> bytes:\n    envelope = copy.deepcopy(data)\n    envelope["signatures"] = []\n    metadata = {field: signature.get(field) for field in SIGNATURE_METADATA_FIELDS}\n    document = {"domain": DOMAIN[:-1].decode("ascii"), "envelope": envelope, "signature_metadata": metadata}\n    return DOMAIN + json.dumps(document, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")\n\n\ndef sha256_digest(value: bytes) -> str:\n    return "sha256:" + hashlib.sha256(value).hexdigest()\n\n\ndef command_signature_verifier(command: Sequence[str]) -> SignatureVerifier:\n    if not command:\n        fail("signature verifier command missing")\n\n    def verify(signature: dict[str, Any], actor: dict[str, Any], payload: bytes) -> bool:\n        request = {\n            "schema": "heptabao.signature-verification-request.v1",\n            "payload_base64": base64.b64encode(payload).decode("ascii"),\n            "payload_digest": sha256_digest(payload),\n            "actor": actor,\n            "signature": signature,\n        }\n        completed = subprocess.run(\n            list(command), input=json.dumps(request, sort_keys=True), text=True,\n            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,\n        )\n        if completed.returncode != 0:\n            return False\n        try:\n            response = json.loads(completed.stdout)\n        except json.JSONDecodeError:\n            return False\n        return response == {\n            "verified": True,\n            "signer_id": signature["signer_id"],\n            "role": signature["role"],\n            "organization": actor["organization"],\n            "credential_id": actor["credential_id"],\n            "credential_status": "CURRENT_SCOPE_BOUND",\n            "key_id": signature["key_id"],\n            "trust_root_id": signature["trust_root_id"],\n            "payload_digest": signature["payload_digest"],\n            "revocation_status": "CURRENT",\n            "transparency_status": "INCLUDED",\n        }\n\n    return verify\n\n\ndef validate_envelope(\n    data: dict[str, Any], *, require_closure: bool = False,\n    expected_source: dict[str, str] | None = None, now: datetime | None = None,\n    signature_verifier: SignatureVerifier | None = None,\n) -> None:\n    validate_schema(data)\n    if data.get("schema") != SCHEMA_NAME:\n        fail("schema mismatch")\n    blocker = data.get("blocker_id")\n    if blocker not in ALLOWED_BLOCKERS:\n        fail("unsupported blocker")\n    if data.get("repository") != {"id": REPOSITORY_ID, "full_name": REPOSITORY_FULL_NAME}:\n        fail("repository identity mismatch")\n    if data.get("claims") != {\n        "qualification": False, "compatibility_claim": False, "selected_candidates": [],\n        "selection_effect": "NONE", "production_authority": False, "migration_authority": False,\n        "release_authority": False, "authority_effect": "NONE",\n    }:\n        fail("authority drift")\n    if not require_closure:\n        return\n    if data.get("state") != "ACCEPTED":\n        fail("closure requires ACCEPTED")\n    if expected_source is None:\n        fail("closure requires caller-supplied exact source expectations")\n    source = data["source"]\n    source_keys = (\n        "commit", "tree", "base_commit", "merge_commit", "merge_tree",\n        "merge_parent_one", "merge_parent_two", "plan_digest", "manifest_digest",\n    )\n    if set(expected_source) != set(source_keys):\n        fail("expected source must contain every exact identity and digest")\n    for key in source_keys:\n        value = source.get(key)\n        pattern = DIGEST if key.endswith("_digest") else HEX40\n        if not isinstance(value, str) or not pattern.fullmatch(value):\n            fail(f"source.{key}: exact value required")\n        if value != expected_source[key]:\n            fail(f"source.{key}: expected-source mismatch")\n    if source["merge_parent_one"] != source["base_commit"] or source["merge_parent_two"] != source["commit"]:\n        fail("merge parent declaration mismatch")\n    if source["merge_commit"] in {source["commit"], source["base_commit"]}:\n        fail("merge identity must be distinct from both parents")\n\n    scope = data["scope"]\n    if not scope or len(scope) != len(set(scope)):\n        fail("closure scope must be non-empty and unique")\n    for index, value in enumerate(scope):\n        non_placeholder(value, f"scope[{index}]")\n\n    current = now or datetime.now(timezone.utc)\n    actors = data["actors"]\n    roles: dict[str, dict[str, Any]] = {}\n    actor_ids: set[str] = set()\n    credential_ids: set[str] = set()\n    for index, actor in enumerate(actors):\n        stable_id = non_placeholder(actor.get("stable_id"), f"actors[{index}].stable_id")\n        role = non_placeholder(actor.get("role"), f"actors[{index}].role")\n        non_placeholder(actor.get("organization"), f"actors[{index}].organization")\n        credential_id = non_placeholder(actor.get("credential_id"), f"actors[{index}].credential_id")\n        non_placeholder(actor.get("credential_issuer"), f"actors[{index}].credential_issuer")\n        non_placeholder(actor.get("revocation_authority"), f"actors[{index}].revocation_authority")\n        credential_not_before = parse_time(\n            actor.get("credential_not_before"), f"actors[{index}].credential_not_before"\n        )\n        credential_not_after = parse_time(\n            actor.get("credential_not_after"), f"actors[{index}].credential_not_after"\n        )\n        if credential_not_before > current or credential_not_after <= current or credential_not_after <= credential_not_before:\n            fail(f"actors[{index}]: accountable credential is not current")\n        if actor.get("conflicts") != []:\n            fail(f"{role}: unresolved conflicts")\n        if stable_id in actor_ids:\n            fail("actor identities must be distinct")\n        if credential_id in credential_ids:\n            fail("actor credential identities must be distinct")\n        if role in roles:\n            fail("actor roles must be unique")\n        actor_ids.add(stable_id)\n        credential_ids.add(credential_id)\n        roles[role] = actor\n        if role in INDEPENDENT_ROLES and actor.get("independent") is not True:\n            fail(f"{role}: independence not affirmed")\n    missing_roles = REQUIRED_ROLES[blocker] - set(roles)\n    if missing_roles:\n        fail(f"missing roles: {sorted(missing_roles)}")\n\n    separation = data["separation"]\n    expected_separation = SEPARATION_KEYS[blocker]\n    if set(separation) != expected_separation:\n        fail(f"separation key mismatch: expected {sorted(expected_separation)}")\n    for key in sorted(expected_separation):\n        non_placeholder(separation[key], f"separation.{key}")\n    for left, right in UNEQUAL_SEPARATION_PAIRS[blocker]:\n        if separation[left] == separation[right]:\n            fail(f"shared control prohibited: {left} == {right}")\n\n    checks = data["checks"]\n    case_ids: set[str] = set()\n    for index, check in enumerate(checks):\n        case_id = non_placeholder(check.get("case_id"), f"checks[{index}].case_id")\n        if case_id in case_ids:\n            fail("duplicate check case")\n        case_ids.add(case_id)\n        if check.get("status") != "PASS":\n            fail(f"{case_id}: non-PASS status")\n        if not isinstance(check.get("evidence_digest"), str) or not DIGEST.fullmatch(check["evidence_digest"]):\n            fail(f"{case_id}: evidence digest missing")\n    missing_cases = REQUIRED_CASES[blocker] - case_ids\n    if missing_cases:\n        fail(f"required cases missing: {sorted(missing_cases)}")\n\n    artifacts = data["artifacts"]\n    artifact_kinds: set[str] = set()\n    for index, artifact in enumerate(artifacts):\n        kind = non_placeholder(artifact.get("kind"), f"artifacts[{index}].kind")\n        if kind in artifact_kinds:\n            fail("duplicate artifact kind")\n        artifact_kinds.add(kind)\n        non_placeholder(artifact.get("name"), f"artifacts[{index}].name")\n        if not isinstance(artifact.get("digest"), str) or not DIGEST.fullmatch(artifact["digest"]):\n            fail(f"artifacts[{index}].digest invalid")\n        custody = non_placeholder(artifact.get("custody_uri"), f"artifacts[{index}].custody_uri")\n        if not (custody.startswith("urn:") or custody.startswith("https://")):\n            fail(f"artifacts[{index}].custody_uri must be an absolute URN or HTTPS URI")\n    missing_artifacts = REQUIRED_ARTIFACT_KINDS[blocker] - artifact_kinds\n    if missing_artifacts:\n        fail(f"required artifact kinds missing: {sorted(missing_artifacts)}")\n\n    finding_ids: set[str] = set()\n    for finding in data["findings"]:\n        finding_id = non_placeholder(finding.get("id"), "findings.id")\n        if finding_id in finding_ids:\n            fail("duplicate finding id")\n        finding_ids.add(finding_id)\n        if finding.get("severity") in {"CRITICAL", "HIGH", "UNCLASSIFIED"} and finding.get("state") != "CLOSED":\n            fail("critical/high/unclassified finding remains open")\n\n    if signature_verifier is None:\n        fail("closure requires an external cryptographic signature verifier")\n    signatures = data["signatures"]\n    signed_ids: set[str] = set()\n    signed_roles: set[str] = set()\n    key_ids: set[str] = set()\n    for index, signature in enumerate(signatures):\n        signer_id = non_placeholder(signature.get("signer_id"), f"signatures[{index}].signer_id")\n        role = non_placeholder(signature.get("role"), f"signatures[{index}].role")\n        key_id = non_placeholder(signature.get("key_id"), f"signatures[{index}].key_id")\n        algorithm = non_placeholder(signature.get("algorithm"), f"signatures[{index}].algorithm")\n        if any(token in algorithm.lower() for token in ("test", "mock", "example")):\n            fail("test/mock/example signature algorithm prohibited in closure mode")\n        if signer_id in signed_ids or role in signed_roles or key_id in key_ids:\n            fail("signer identities, roles and keys must be distinct")\n        signed_ids.add(signer_id); signed_roles.add(role); key_ids.add(key_id)\n        actor = roles.get(role)\n        if actor is None or actor["stable_id"] != signer_id:\n            fail("signature signer and role must bind to one declared actor")\n        for field in ("trust_root_id", "signature"):\n            non_placeholder(signature.get(field), f"signatures[{index}].{field}")\n        for field in ("transparency_checkpoint_digest", "revocation_evidence_digest", "payload_digest"):\n            value = signature.get(field)\n            if not isinstance(value, str) or not DIGEST.fullmatch(value):\n                fail(f"signatures[{index}].{field}: exact digest required")\n        signed_at = parse_time(signature.get("signed_at"), f"signatures[{index}].signed_at")\n        expires_at = parse_time(signature.get("expires_at"), f"signatures[{index}].expires_at")\n        if signed_at > current or expires_at <= current or expires_at <= signed_at:\n            fail("signature freshness invalid")\n        payload = signing_payload(data, signature)\n        if signature["payload_digest"] != sha256_digest(payload):\n            fail("signature payload digest mismatch")\n        if not signature_verifier(signature, actor, payload):\n            fail("external cryptographic signature and accountable-role verification failed")\n    missing_signatures = REQUIRED_ROLES[blocker] - signed_roles\n    if missing_signatures:\n        fail(f"required role signatures missing: {sorted(missing_signatures)}")\n\n\ndef main() -> int:\n    parser = argparse.ArgumentParser()\n    parser.add_argument("paths", nargs="+")\n    parser.add_argument("--require-closure", action="store_true")\n    for field in (\n        "commit", "tree", "base-commit", "merge-commit", "merge-tree",\n        "merge-parent-one", "merge-parent-two", "plan-digest", "manifest-digest",\n    ):\n        parser.add_argument(f"--expected-{field}")\n    parser.add_argument("--signature-verifier")\n    parser.add_argument("--signature-verifier-arg", action="append", default=[])\n    args = parser.parse_args()\n    expected = None\n    verifier = None\n    if args.require_closure:\n        expected = {\n            "commit": args.expected_commit, "tree": args.expected_tree,\n            "base_commit": args.expected_base_commit, "merge_commit": args.expected_merge_commit,\n            "merge_tree": args.expected_merge_tree, "merge_parent_one": args.expected_merge_parent_one,\n            "merge_parent_two": args.expected_merge_parent_two, "plan_digest": args.expected_plan_digest,\n            "manifest_digest": args.expected_manifest_digest,\n        }\n        if any(value is None for value in expected.values()):\n            parser.error("all expected source identities and digests are required with --require-closure")\n        if not args.signature_verifier:\n            parser.error("--signature-verifier is required with --require-closure")\n        verifier = command_signature_verifier([args.signature_verifier, *args.signature_verifier_arg])\n    for raw_path in args.paths:\n        path = Path(raw_path)\n        value = json.loads(path.read_text(encoding="utf-8"))\n        validate_envelope(value, require_closure=args.require_closure, expected_source=expected, signature_verifier=verifier)\n        print(f"PASS {path}")\n    return 0\n\n\nif __name__ == "__main__":\n    raise SystemExit(main())\n'

def external_test_source() -> str:
    return 'from __future__ import annotations\n\nimport copy\nimport importlib.util\nimport json\nimport unittest\nfrom datetime import datetime, timezone\nfrom pathlib import Path\n\nROOT = Path(__file__).resolve().parents[2]\nSPEC = importlib.util.spec_from_file_location(\n    "external_validator", ROOT / "scripts/validate_external_completion_evidence_v1.py"\n)\nassert SPEC and SPEC.loader\nVALIDATOR = importlib.util.module_from_spec(SPEC)\nSPEC.loader.exec_module(VALIDATOR)\nDIGEST = "sha256:" + "a" * 64\nEXPECTED = {\n    "commit": "1" * 40,\n    "tree": "2" * 40,\n    "base_commit": "0" * 40,\n    "merge_commit": "3" * 40,\n    "merge_tree": "4" * 40,\n    "merge_parent_one": "0" * 40,\n    "merge_parent_two": "1" * 40,\n    "plan_digest": "sha256:" + "b" * 64,\n    "manifest_digest": "sha256:" + "c" * 64,\n}\nNOW = datetime(2026, 9, 2, tzinfo=timezone.utc)\n\n\ndef accepted_ext007() -> dict:\n    roles = sorted(VALIDATOR.REQUIRED_ROLES["HB-BLK-EXT-007"])\n    actors = [\n        {\n            "stable_id": f"actor-{index:03d}",\n            "role": role,\n            "organization": f"Independent Lab {index}",\n            "independent": True,\n            "conflicts": [],\n            "credential_id": f"credential-{index:03d}",\n            "credential_issuer": f"Independent Credential Authority {index}",\n            "credential_not_before": "2026-09-01T00:00:00Z",\n            "credential_not_after": "2027-09-01T00:00:00Z",\n            "revocation_authority": f"urn:revocation:authority:{index:03d}",\n        }\n        for index, role in enumerate(roles, 1)\n    ]\n    separation = {\n        "primary_credential_root": "urn:primary:credential-root",\n        "reproduction_credential_root": "urn:reproduction:credential-root",\n        "primary_runner_admin": "urn:primary:runner-admin",\n        "reproduction_runner_admin": "urn:reproduction:runner-admin",\n        "primary_cache_admin": "urn:primary:cache-admin",\n        "reproduction_cache_admin": "urn:reproduction:cache-admin",\n        "primary_artifact_custody": "urn:primary:artifact-custody",\n        "reproduction_artifact_custody": "urn:reproduction:artifact-custody",\n        "primary_signing_root": "urn:primary:signing-root",\n        "reproduction_signing_root": "urn:reproduction:signing-root",\n        "primary_network_egress": "urn:primary:network-egress",\n        "reproduction_network_egress": "urn:reproduction:network-egress",\n    }\n    value = {\n        "schema": "heptabao.external-completion-evidence.v1",\n        "blocker_id": "HB-BLK-EXT-007",\n        "state": "ACCEPTED",\n        "repository": {"id": 1349115072, "full_name": "TrillionniumFoundation/HeptaBao"},\n        "source": dict(EXPECTED),\n        "scope": ["exact head and prospective merge full reproduction"],\n        "actors": actors,\n        "separation": separation,\n        "checks": [\n            {"case_id": case_id, "status": "PASS", "evidence_digest": DIGEST}\n            for case_id in sorted(VALIDATOR.REQUIRED_CASES["HB-BLK-EXT-007"])\n        ],\n        "artifacts": [\n            {\n                "kind": kind,\n                "name": kind.lower().replace("_", " "),\n                "digest": DIGEST,\n                "custody_uri": f"urn:lab:artifact:{kind.lower()}",\n                "classification": "RESTRICTED_REFERENCE",\n            }\n            for kind in sorted(VALIDATOR.REQUIRED_ARTIFACT_KINDS["HB-BLK-EXT-007"])\n        ],\n        "findings": [],\n        "signatures": [\n            {\n                "signer_id": actor["stable_id"],\n                "role": actor["role"],\n                "key_id": f"key-{index:03d}",\n                "algorithm": "ed25519-profile-v1",\n                "signed_at": "2026-09-01T00:00:00Z",\n                "expires_at": "2027-09-01T00:00:00Z",\n                "trust_root_id": f"trust-root-{index:03d}",\n                "transparency_checkpoint_digest": "sha256:" + "d" * 64,\n                "revocation_evidence_digest": "sha256:" + "e" * 64,\n                "payload_digest": DIGEST,\n                "signature": ("ab" if index == 1 else "cd") * 32,\n            }\n            for index, actor in enumerate(actors, 1)\n        ],\n        "claims": {\n            "qualification": False,\n            "compatibility_claim": False,\n            "selected_candidates": [],\n            "selection_effect": "NONE",\n            "production_authority": False,\n            "migration_authority": False,\n            "release_authority": False,\n            "authority_effect": "NONE",\n        },\n    }\n    for signature in value["signatures"]:\n        signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n    return value\n\n\ndef accepting_verifier(signature: dict, actor: dict, payload: bytes) -> bool:\n    return (\n        actor["stable_id"] == signature["signer_id"]\n        and actor["role"] == signature["role"]\n        and signature["payload_digest"] == VALIDATOR.sha256_digest(payload)\n    )\n\n\nclass ExternalCompletionEvidenceTests(unittest.TestCase):\n    def validate(self, value: dict, *, verifier=accepting_verifier) -> None:\n        VALIDATOR.validate_envelope(\n            value,\n            require_closure=True,\n            expected_source=EXPECTED,\n            now=NOW,\n            signature_verifier=verifier,\n        )\n\n    def test_bounded_valid_closure_envelope_passes_with_external_verifier(self) -> None:\n        self.validate(accepted_ext007())\n\n    def test_templates_are_schema_shaped_but_not_closure(self) -> None:\n        for path in sorted((ROOT / "qualifications/external/templates").glob("*.json")):\n            value = json.loads(path.read_text(encoding="utf-8"))\n            VALIDATOR.validate_envelope(value, require_closure=False)\n            with self.assertRaises(ValueError):\n                self.validate(value)\n\n    def test_self_asserted_validity_without_external_verifier_fails(self) -> None:\n        value = accepted_ext007()\n        with self.assertRaisesRegex(ValueError, "external cryptographic signature verifier"):\n            self.validate(value, verifier=None)\n\n    def test_schema_rejects_unknown_self_asserted_verification_field(self) -> None:\n        value = accepted_ext007()\n        value["signatures"][0]["verification"] = "VALID"\n        with self.assertRaisesRegex(ValueError, "schema validation failed"):\n            self.validate(value)\n\n    def test_tampered_payload_fails_digest_binding(self) -> None:\n        value = accepted_ext007()\n        value["scope"].append("tampered scope")\n        with self.assertRaisesRegex(ValueError, "payload digest mismatch"):\n            self.validate(value)\n\n    def test_external_verifier_rejection_fails_closed(self) -> None:\n        with self.assertRaisesRegex(ValueError, "external cryptographic"):\n            self.validate(accepted_ext007(), verifier=lambda _signature, _actor, _payload: False)\n\n    def test_missing_required_case_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["checks"].pop()\n        for signature in value["signatures"]:\n            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n        with self.assertRaisesRegex(ValueError, "required cases missing"):\n            self.validate(value)\n\n    def test_missing_required_artifact_kind_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["artifacts"].pop()\n        for signature in value["signatures"]:\n            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n        with self.assertRaisesRegex(ValueError, "required artifact kinds missing"):\n            self.validate(value)\n\n    def test_non_pass_case_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["checks"][0]["status"] = "UNKNOWN"\n        with self.assertRaises(ValueError):\n            self.validate(value)\n\n    def test_shared_actor_identity_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["actors"][1]["stable_id"] = value["actors"][0]["stable_id"]\n        with self.assertRaises(ValueError):\n            self.validate(value)\n\n\n    def test_actor_credential_is_schema_mandatory(self) -> None:\n        value = accepted_ext007()\n        del value["actors"][0]["credential_id"]\n        with self.assertRaisesRegex(ValueError, "schema validation failed"):\n            self.validate(value)\n\n    def test_expired_actor_credential_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["actors"][0]["credential_not_after"] = "2026-09-01T00:00:00Z"\n        for signature in value["signatures"]:\n            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n        with self.assertRaisesRegex(ValueError, "accountable credential is not current"):\n            self.validate(value)\n\n    def test_duplicate_actor_credential_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["actors"][1]["credential_id"] = value["actors"][0]["credential_id"]\n        for signature in value["signatures"]:\n            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n        with self.assertRaisesRegex(ValueError, "credential identities must be distinct"):\n            self.validate(value)\n\n    def test_signature_must_bind_to_declared_actor_and_role(self) -> None:\n        value = accepted_ext007()\n        value["signatures"][0]["signer_id"] = "undeclared-signer"\n        with self.assertRaisesRegex(ValueError, "declared actor"):\n            self.validate(value)\n\n    def test_shared_primary_and_reproduction_control_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["separation"]["reproduction_runner_admin"] = value["separation"]["primary_runner_admin"]\n        for signature in value["signatures"]:\n            signature["payload_digest"] = VALIDATOR.sha256_digest(VALIDATOR.signing_payload(value, signature))\n        with self.assertRaisesRegex(ValueError, "shared control prohibited"):\n            self.validate(value)\n\n    def test_source_or_parent_drift_fails_closed(self) -> None:\n        for field in ("tree", "merge_parent_two"):\n            value = accepted_ext007()\n            value["source"][field] = "f" * 40\n            with self.assertRaises(ValueError):\n                self.validate(value)\n\n    def test_expired_signature_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["signatures"][0]["expires_at"] = "2026-09-01T00:00:00Z"\n        with self.assertRaises(ValueError):\n            self.validate(value)\n\n    def test_test_algorithm_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["signatures"][0]["algorithm"] = "test-ed25519-profile"\n        value["signatures"][0]["payload_digest"] = VALIDATOR.sha256_digest(\n            VALIDATOR.signing_payload(value, value["signatures"][0])\n        )\n        with self.assertRaisesRegex(ValueError, "test/mock/example"):\n            self.validate(value)\n\n    def test_authority_elevation_fails_closed(self) -> None:\n        value = accepted_ext007()\n        value["claims"]["production_authority"] = True\n        with self.assertRaises(ValueError):\n            self.validate(value)\n\n\nif __name__ == "__main__":\n    unittest.main()\n'

def module_test_source() -> str:
    return textwrap.dedent(
        r'''from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("renderer", ROOT / "scripts/render_plan_v1_4_7.py")
assert SPEC and SPEC.loader
RENDERER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RENDERER)


class ModuleSourceTruthTests(unittest.TestCase):
    def test_snapshot_matches_exact_workspace(self) -> None:
        expected = RENDERER.build_truth(ROOT)
        actual = yaml.safe_load((ROOT / RENDERER.TRUTH_PATH).read_text(encoding="utf-8"))
        self.assertEqual(expected, actual)
        self.assertEqual(19, actual["module_count"])

    def test_every_module_guide_generated_sections_are_current(self) -> None:
        truth = RENDERER.build_truth(ROOT)
        for module in truth["modules"]:
            path = ROOT / module["module_guide"]
            self.assertEqual(RENDERER.module_doc_expected(ROOT, module), path.read_text(encoding="utf-8"))

    def test_workspace_dependency_and_public_surface_are_nonempty(self) -> None:
        truth = RENDERER.build_truth(ROOT)
        self.assertTrue(any(module["internal_dependencies"] for module in truth["modules"]))
        self.assertTrue(all(module["source_files"] for module in truth["modules"]))
        self.assertTrue(any(module["public_items"] for module in truth["modules"]))
        self.assertTrue(any(module["test_functions"] for module in truth["modules"]))


if __name__ == "__main__":
    unittest.main()
'''
    ).lstrip()


def plan_validator_source() -> str:
    return textwrap.dedent(
        r'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
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
BASELINE_COMMIT = "54d524214df443752a2ecaeff6d4a05625bf52c7"
BASELINE_TREE = "c22288f561fdd711e908ce8a70c0116601d519e5"
REQUIRED = [
    "docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md",
    "planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml",
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml",
    "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml",
    "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml",
    "planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml",
    "planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml",
    "docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md",
    "docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md",
    "schemas/heptabao_external_completion_evidence_v1.schema.json",
    "scripts/render_plan_v1_4_7.py",
    "scripts/validate_external_completion_evidence_v1.py",
    "tests/plan/test_external_completion_evidence_v1.py",
    "tests/plan/test_module_source_truth_v1_4_7.py",
    "tests/plan/test_plan_v1_4_7.py",
    "qualifications/external/README.md",
    ".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_yaml(path: str) -> dict:
    return yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))


def main() -> int:
    missing = [path for path in REQUIRED if not (ROOT / path).is_file()]
    if missing:
        raise SystemExit(f"missing V1.4.7 files: {missing}")
    status = load_yaml("planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml")
    blockers = load_yaml("planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml")
    receipt = load_yaml("planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml")
    admission = load_yaml("planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml")
    for name, value in (("status", status), ("blockers", blockers), ("receipt", receipt), ("admission", admission)):
        if value.get("claims") != CLAIMS:
            raise SystemExit(f"{name}: authority drift")
    if status.get("source_baseline") != {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE}:
        raise SystemExit("status: baseline drift")
    expected_closed = [f"HB-BLK-REPO-{index:03d}" for index in range(49, 59)]
    if receipt.get("closed_repository_blockers") != expected_closed:
        raise SystemExit("post-merge receipt: repository blocker set mismatch")
    if receipt.get("external_or_control_blockers_closed") != []:
        raise SystemExit("post-merge receipt overclaims external closure")
    added = blockers.get("added_blockers", [])
    if [item.get("id") for item in added] != [f"HB-BLK-REPO-{index:03d}" for index in range(59, 63)]:
        raise SystemExit("V1.4.7 blocker set mismatch")
    if any(item.get("state") != "IMPLEMENTED_SOURCE_REVIEW_REQUIRED" for item in added):
        raise SystemExit("V1.4.7 blocker state must remain review-required")
    current = (ROOT / "docs/CURRENT_DOCUMENTATION.md").read_text(encoding="utf-8")
    for token in (
        "HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md",
        "HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml",
        "MODULE_DOCUMENTATION_STANDARD_V2.md",
        "HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md",
    ):
        if token not in current:
            raise SystemExit(f"current documentation missing {token}")
    workflow = (ROOT / ".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml").read_text(encoding="utf-8")
    if "pull_request:" not in workflow or "push:" in workflow:
        raise SystemExit("V1.4.7 workflow must be pull-request-only")
    if "exact-head" not in workflow or "prospective-merge" not in workflow:
        raise SystemExit("V1.4.7 workflow source identities missing")
    manifest = load_yaml("planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml")
    if manifest.get("claims") != CLAIMS:
        raise SystemExit("manifest authority drift")
    for item in manifest.get("files", []):
        path = ROOT / item["path"]
        if not path.is_file() or sha256(path) != item["sha256"]:
            raise SystemExit(f"manifest mismatch: {item['path']}")
    subprocess.run([sys.executable, str(ROOT / "scripts/render_plan_v1_4_7.py"), "--check"], check=True, cwd=ROOT)
    spec = importlib.util.spec_from_file_location(
        "external_validator", ROOT / "scripts/validate_external_completion_evidence_v1.py"
    )
    assert spec and spec.loader
    validator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(validator)
    for path in sorted((ROOT / "qualifications/external/templates").glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        validator.validate_envelope(value, require_closure=False)
        try:
            validator.validate_envelope(value, require_closure=True)
        except ValueError:
            pass
        else:
            raise SystemExit(f"template was admitted as closure: {path}")
    try:
        tree = subprocess.check_output(["git", "rev-parse", f"{BASELINE_COMMIT}^{{tree}}"], cwd=ROOT, text=True).strip()
        if tree != BASELINE_TREE:
            raise SystemExit("baseline Git tree mismatch")
        subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"], cwd=ROOT, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError) as error:
        raise SystemExit(f"baseline commit unavailable: {error}")
    print("PASS HeptaBao V1.4.7 post-merge truth and external admission")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main())
'''
    ).lstrip()


def plan_test_source() -> str:
    return textwrap.dedent(
        r'''from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


class PlanV147Tests(unittest.TestCase):
    def test_previous_repository_blockers_are_closed_without_external_overclaim(self) -> None:
        receipt = yaml.safe_load(
            (ROOT / "planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text(encoding="utf-8")
        )
        self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(49, 59)], receipt["closed_repository_blockers"])
        self.assertEqual([], receipt["external_or_control_blockers_closed"])
        self.assertFalse(receipt["claims"]["qualification"])

    def test_new_repository_blockers_are_source_implemented_review_required(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml").read_text(encoding="utf-8"))
        self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(59, 63)], [item["id"] for item in value["added_blockers"]])
        self.assertTrue(all(item["state"] == "IMPLEMENTED_SOURCE_REVIEW_REQUIRED" for item in value["added_blockers"]))

    def test_external_and_control_blockers_remain_open(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml").read_text(encoding="utf-8"))
        self.assertEqual(
            ["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{i:03d}" for i in range(1, 8)]],
            value["external_open"],
        )
        self.assertEqual("NONE", value["claims"]["authority_effect"])

    def test_current_workflow_is_read_only_and_pr_only(self) -> None:
        text = (ROOT / ".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml").read_text(encoding="utf-8")
        self.assertIn("contents: read", text)
        self.assertIn("pull_request:", text)
        self.assertNotIn("push:", text)
        self.assertIn("exact-head", text)
        self.assertIn("prospective-merge", text)


if __name__ == "__main__":
    unittest.main()
'''
    ).lstrip()


def workflow_source() -> str:
    return textwrap.dedent(
        '''name: HeptaBao V1.4.7 post-merge truth and external admission

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches:
      - integration/v1.4.4-technical-candidate

permissions:
  contents: read

concurrency:
  group: v1.4.7-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
  cancel-in-progress: true

jobs:
  validate:
    name: v1.4.7 / pull_request / ${{ matrix.source_kind }}
    runs-on: ubuntu-24.04
    timeout-minutes: 120
    permissions:
      contents: read
      pull-requests: read
    strategy:
      fail-fast: false
      matrix:
        source_kind: [exact-head, prospective-merge]
    env:
      SOURCE_KIND: ${{ matrix.source_kind }}
      SOURCE_SHA: ${{ matrix.source_kind == 'prospective-merge' && github.sha || github.event.pull_request.head.sha }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
      BASE_SHA: ${{ github.event.pull_request.base.sha }}
      V147_BASELINE: 54d524214df443752a2ecaeff6d4a05625bf52c7
    steps:
      - name: Checkout immutable source identity
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
        with:
          ref: ${{ env.SOURCE_SHA }}
          fetch-depth: 0
          persist-credentials: false

      - name: Bind exact head or prospective merge
        shell: bash
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
          git merge-base --is-ancestor "$V147_BASELINE" "$HEAD_SHA"
          if [[ "$SOURCE_KIND" == "prospective-merge" ]]; then
            read -r merge parent_one parent_two extra <<<"$(git rev-list --parents -n 1 HEAD)"
            test "$merge" = "$SOURCE_SHA"
            test "$parent_one" = "$BASE_SHA"
            test "$parent_two" = "$HEAD_SHA"
            test -z "${extra:-}"
          else
            test "$SOURCE_SHA" = "$HEAD_SHA"
          fi
          test -z "$(git status --porcelain=v1 --untracked-files=all)"
          printf 'source_kind=%s\\nsource_sha=%s\\ntree=%s\\n' "$SOURCE_KIND" "$SOURCE_SHA" "$(git rev-parse HEAD^{tree})"

      - name: Install exact Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-plan.txt

      - name: Validate plans documentation and external admission
        shell: bash
        run: |
          set -euo pipefail
          python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
          python scripts/validate_plan_v1_4_7.py
          python -m unittest discover -s tests/plan -p 'test_*v1_4_7.py' -v
          python -m unittest discover -s tests/plan -p 'test_external_completion_evidence_v1.py' -v
          python -m unittest discover -s tests/plan -p 'test_*.py' -v
          python scripts/validate_plan_v1_4_6.py
          python -m unittest discover -s tests/plan -p 'test_plan_v1_4_6.py' -v
          python scripts/validate_plan_v1_4_5.py
          python -m unittest discover -s tests/plan -p 'test_plan_v1_4_5.py' -v
          python scripts/validate_module_documentation_v1_4_4.py
          python -m unittest discover -s tests/plan -p 'test_module_documentation_v1_4_4.py' -v
          python -m unittest discover -s tests/platform -p 'test_*.py' -v
          python -m unittest discover -s tests/oracle -p 'test_*.py' -v

      - name: Install exact Rust 1.98
        shell: bash
        run: |
          set -euo pipefail
          rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
          rustc +1.98.0 --version --verbose
          cargo +1.98.0 --version --verbose

      - name: Validate locked Rust workspace
        shell: bash
        run: |
          set -euo pipefail
          cargo +1.98.0 fmt --all -- --check
          cargo +1.98.0 test --locked --workspace --all-targets
          cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings

      - name: Confirm fail-closed authority boundary
        shell: bash
        run: |
          set -euo pipefail
          grep -R "authority_effect: NONE" planning/HEPTABAO_*V1_4_7*.yaml planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml
          ! grep -R "production_authority: true\\|release_authority: true\\|migration_authority: true\\|compatibility_claim: true" \
            planning/HEPTABAO_*V1_4_7*.yaml planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml
'''
    ).lstrip()


def current_documentation() -> str:
    return textwrap.dedent(
        '''# HeptaBao Current Documentation

This page is the single current-entry portal. A newer row supersedes an older row only for the named subject; historical documents remain immutable evidence and are not silently rewritten.

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md` |
| current status | `planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml` |
| post-merge V1.4.6 closure receipt | `planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| module documentation standard | `docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md` |
| module index | `docs/modules/README.md` |
| machine-bound module source truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml` |
| external completion admission protocol | `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md` |
| external completion admission catalog | `planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml` |
| current exact-head/merge gate | `.github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml` |

## Inherited immutable set

| Subject | Inherited document |
|---|---|
| V1.4.6 plan | `docs/plan/HEPTABAO_PLAN_V1_4_6_AUTHORITATIVE_RECOVERY_CLOSURE.md` |
| V1.4.6 status | `planning/HEPTABAO_V1_4_6_AUTHORITATIVE_RECOVERY_STATUS.yaml` |
| V1.4.6 blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_6.yaml` |
| V1.4.6 normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_6.yaml` |
| V1.4.6 authoritative recovery protocol | `docs/recovery/HEPTABAO_AUTHORITATIVE_RECOVERY_PROTOCOL_V1.md` |
| V1.4.6 recovery gate | `.github/workflows/plan-v1.4.6-authoritative-recovery-closure.yml` |
| V1.4.5 security regression gate | `.github/workflows/plan-v1.4.5-security-invariant-closure.yml` |
| V1.4.4 module existence gate | `.github/workflows/plan-v1.4.4-module-documentation.yml` |

## Supersession chain

```text
V1.4.2 anchored recovery foundation
  → V1.4.3 descriptor anchoring/writer fencing
  → V1.4.4 complete current-crate documentation
  → V1.4.5 security invariant closure
  → V1.4.6 authoritative recovery closure
  → V1.4.7 post-merge truth and external admission
```

## V1.4.6 post-merge disposition

V1.4.6 exact head `837668cb879683bc60808584d2ebdedd42a397aa` and prospective merge `54d524214df443752a2ecaeff6d4a05625bf52c7` passed their required repository gates. The same exact head received a current GitHub approval, and the signed GitHub merge has tree `c22288f561fdd711e908ce8a70c0116601d519e5`. The V1.4.7 post-merge receipt therefore closes only `HB-BLK-REPO-049` through `HB-BLK-REPO-058` in repository-controlled scope. It does not create an accountable role receipt or close any control/external blocker.

## V1.4.7 reading rule

Each current Cargo workspace crate has one module guide. Public lexical declarations, workspace-internal dependencies, source-file digests and discovered test functions are generated from the exact candidate source and bound in `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml`. Generated tables are source truth for the exact candidate; they do not promise API stability, compatibility or production support.

External completion documents are admitted only through the strict V1.4.7 envelope and validator. Templates are deliberately `UNEXECUTED` and are prohibited from closing a blocker. A green repository workflow cannot manufacture legal advice, independent identities, 24x7 operation, isolated key custody, restricted Oracle transfer, destructive power-cut evidence or separately controlled reproduction.

## Open authority boundary

`HB-BLK-CTRL-001` and `HB-BLK-EXT-001` through `HB-BLK-EXT-007` remain open until live, current, independently verifiable completion objects are admitted. Product composition, compatibility, platform qualification, provider selection, migration, production and release authority remain false.
'''
    ).lstrip()



def current_readme() -> str:
    return textwrap.dedent(
        '''# HeptaBao

HeptaBao is an independent clean-room Rust reimplementation program for an OpenBao-compatible secrets-management server.

## Current truth

- Current plan: **V1.4.7 post-merge truth and external admission**.
- Current integration baseline: signed **V1.4.6 authoritative recovery closure** merge `54d524214df443752a2ecaeff6d4a05625bf52c7`, tree `c22288f561fdd711e908ce8a70c0116601d519e5`.
- Inherited immutable baselines: **V1.4.5 security invariant closure** and **V1.4.4** module-documentation closure recorded by `planning/HEPTABAO_MODULE_DOCUMENTATION_COVERAGE_V1_4_4.yaml`.
- Current implemented foundation: the inherited 19-crate safety/recovery kernel, source-bound module documentation, and strict fail-closed external completion admission.
- Current Cargo workspace documentation: **19 / 19** crates have source-bound developer guides under `docs/modules/`.
- Qualification: **false**.
- Compatibility claim: **false**.
- Dependency selections: **none with production authority**.
- Production, migration, release and mixed-cluster authority: **false**.
- Supported production versions: **none**.

The repository is **not production-deployable** and is **not a production-deployable secrets server**. Do not use it to protect real secrets and do not place real tokens, unseal shares, recovery keys, private keys or production snapshots in source, tests or CI.

## Current normative entry points

1. `docs/CURRENT_DOCUMENTATION.md`
2. `docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md`
3. `planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml`
4. `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml`
5. `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_4_7.yaml`
6. `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml`
7. `docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md`
8. `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md`
9. `planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml`
10. `.github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml`

## Architecture boundary

The current code remains a safety-oriented kernel and loopback-only P0 development server. A production composition root, policy, identity, token, lease, namespace, plugin host, secrets engines, Raft/HA, CLI, Agent, Proxy and full OpenBao compatibility remain later product work. Target documents and unexecuted evidence templates do not imply that those capabilities are implemented or qualified.

## Evidence and authority boundary

Repository-controlled tests can validate source and admission logic but cannot manufacture live branch protection, accountable independent identities, legal disposition, 24x7 operations, isolated signing custody, restricted Oracle transfer, destructive storage-laboratory evidence or independently controlled reproduction. Those blockers close only through externally verified, current, scope-bound completion objects.

## Development

Run the current renderer, current gate and the complete inherited plan/platform/Oracle regressions:

```text
python scripts/render_plan_v1_4_7.py --check
python scripts/validate_plan_v1_4_7.py
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```

Exact current source and prospective-merge identities come from the active pull request and immutable read-only workflows, not from an unversioned `latest` alias.
'''
    ).lstrip()


def module_standard_v2() -> str:
    return textwrap.dedent(
        '''# HeptaBao Module Documentation Standard V2

Status: current normative standard for every Cargo workspace crate.

## Required narrative sections

Every module guide must retain implementation purpose, maturity, dependency direction, public API, state invariants, errors and retry semantics, data formats, security considerations, test strategy, extension rules, operational guidance, known gaps and traceability.

## Machine-bound facts

The following facts are generated from the exact candidate source and may not be maintained as unsupported prose:

1. Cargo manifest SHA-256;
2. all Rust source-file SHA-256 digests;
3. workspace-internal dependency declarations and dependency section;
4. public lexical declarations with source path, line, kind and declaration text;
5. discovered `#[test]` and runtime test functions;
6. exact mapping from Cargo package name to module guide.

The authoritative snapshot is `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml`. Each module guide contains generated Public API and source-truth blocks. `python scripts/render_plan_v1_4_7.py --check` must fail whenever source, dependencies, tests or generated documentation drift.

## Scope boundary

The V2 parser is deliberately described as a bounded lexical Rust inventory. It does not perform Rust name resolution and cannot establish semantic API compatibility. Those limitations must remain explicit; success grants no qualification, compatibility, provider selection or authority.

## Change rule

A source change that affects any generated fact requires regeneration in the same pull request. Hand editing a generated block, deleting an API item from documentation, inventing a test, or retaining a stale dependency graph is a failing condition. Historical narrative remains evidence but may not override a newer generated source fact.

## Review rule

Critical modules require a reviewer to inspect both semantic narrative and generated source facts. Structural presence alone is insufficient. Approval must bind the exact pull-request head and prospective merge identity.
'''
    ).lstrip()


def external_protocol() -> str:
    return '# HeptaBao External Completion Admission Protocol V1\n\n## Purpose\n\nThis protocol admits completion evidence for `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` without converting repository automation, templates or self-assertions into external facts. Closure admission is fail-closed and binds one exact reviewed head, base, two-parent merge, plan digest and normative-manifest digest.\n\n## Envelope and schema\n\nEvery candidate uses `heptabao.external-completion-evidence.v1` and must validate against `schemas/heptabao_external_completion_evidence_v1.schema.json`. Unknown properties are rejected. Non-closure validation checks only shape and immutable authority nonclaims; it never promotes an `UNEXECUTED` or pending object.\n\nClosure mode additionally requires:\n\n- exact head, tree, base, merge, merge tree and ordered merge-parent identities supplied independently by the admitting caller;\n- exact plan and normative-manifest SHA-256 digests supplied independently by the admitting caller;\n- the complete blocker-specific mandatory case inventory, with every case `PASS` and evidence-digest bound;\n- all blocker-specific artifact kinds, each digest bound and held at an absolute URN or HTTPS custody reference;\n- distinct actors for every required role, current issuer-bound accountable credentials, explicit independence and zero unresolved conflicts;\n- blocker-specific control-separation identifiers and explicit inequality between primary and external/control roots;\n- no open Critical, High or Unclassified finding;\n- one payload-bound signature from every required role;\n- a caller-supplied external cryptographic verifier for every signature.\n\n## Signature contract\n\nThe envelope never proves its own signatures. A text field such as `verification: VALID` is prohibited by the schema and cannot close a blocker.\n\nEach signer signs a domain-separated canonical payload:\n\n```text\nHEPTABAO_EXTERNAL_COMPLETION_EVIDENCE_V1\\0\n  || canonical-json({\n       domain,\n       envelope-with-empty-signatures,\n       signature-metadata\n     })\n```\n\nThe signed envelope binds each actor’s stable identity, organization, credential identifier and issuer, credential validity interval and revocation authority. Signature metadata additionally binds signer, accountable role, key, algorithm, signing and expiry times, trust-root identifier, transparency-checkpoint digest and revocation-evidence digest. The envelope carries the resulting payload SHA-256. Admission recomputes it before invoking the verifier.\n\nThe external verifier receives the canonical payload plus signature metadata and bytes. It must independently validate the signature, key role/scope, current trust root, transparency inclusion and revocation state. Closure fails unless the verifier returns an exact result containing:\n\n```text\nverified=true\nmatching signer_id\nmatching accountable role and organization\nmatching current credential_id with credential_status=CURRENT_SCOPE_BOUND\nmatching key_id and trust_root_id\nmatching payload_digest\nrevocation_status=CURRENT\ntransparency_status=INCLUDED\n```\n\nRepository tests may inject a deterministic callback only to test validator control flow. Test, mock or example algorithms are rejected in real closure mode.\n\n## Mandatory case and artifact catalogs\n\nThe validator owns a minimum case catalog and artifact-kind catalog for every blocker. Supplying one generic `PASS` row, omitting a negative/control case, omitting a raw-evidence manifest or relabelling a partial run as complete fails closure. Additional cases and artifacts are allowed, but duplicate IDs/kinds are rejected.\n\nThe catalogs cover, among other things:\n\n- ruleset API readback and blocked bypass/force-push/deletion/look-alike checks;\n- program, security and storage reviews with identity and revocation checks;\n- every required legal scope and signer-authority check;\n- private intake, continuous primary/backup coverage, tabletop and freeze/revocation drills;\n- key ceremonies, transparency, rotation, compromise and consumer revocation;\n- Oracle ACL separation, real behavior captures, deterministic sanitization and signed transfer;\n- controller-proven power cuts, durability boundaries, acknowledged-write preservation, corruption and repeat-recovery controls;\n- independent source acquisition, dependency resolution, full head/merge execution, artifact comparison, normalizer control and divergence review.\n\n## Invocation\n\nPlanning-only shape validation:\n\n```text\npython scripts/validate_external_completion_evidence_v1.py candidate.json\n```\n\nClosure admission requires every expected identity/digest and an external verifier executable:\n\n```text\npython scripts/validate_external_completion_evidence_v1.py \\\n  --require-closure \\\n  --expected-commit <40-hex-head> \\\n  --expected-tree <40-hex-head-tree> \\\n  --expected-base-commit <40-hex-base> \\\n  --expected-merge-commit <40-hex-merge> \\\n  --expected-merge-tree <40-hex-merge-tree> \\\n  --expected-merge-parent-one <40-hex-base> \\\n  --expected-merge-parent-two <40-hex-head> \\\n  --expected-plan-digest sha256:<64-hex> \\\n  --expected-manifest-digest sha256:<64-hex> \\\n  --signature-verifier /isolated/bin/heptabao-signature-verifier \\\n  candidate.json\n```\n\nThe verifier executable reads one JSON verification request on standard input and returns the exact verification result on standard output. Nonzero exit, malformed output, mismatched identity, stale/expired signature, missing transparency inclusion or non-current revocation status fails closure.\n\n## Templates and authority boundary\n\nTemplates under `qualifications/external/templates/` are deliberately `UNEXECUTED`, contain null source identities and no signatures, and can never pass closure mode. Repository ownership, administrator access, CI success, a generated receipt, a self-signed test key or a populated `verification` field cannot manufacture independent people, legal authority, operational coverage, isolated custody, restricted Oracle provenance, destructive laboratory control or independent reproduction.\n\nAdmission closes only the named factual blocker for its exact scope after authentic verification. It does not by itself grant compatibility, provider selection, qualification, production, migration or release authority.\n'

def plan_document() -> str:
    return textwrap.dedent(
        f'''# HeptaBao Plan V1.4.7 — Post-Merge Truth and External Admission

## 1. Baseline

This tranche starts from the signed GitHub merge `{BASELINE_COMMIT}`, tree `{BASELINE_TREE}`, on `integration/v1.4.4-technical-candidate`. It does not reconstruct or supersede that merge with an unreviewed same-tree commit.

## 2. Objectives

1. canonicalize the completed V1.4.6 repository-controlled result after merge;
2. close `HB-BLK-REPO-049` through `HB-BLK-REPO-058` only in repository scope, without closing role, legal, operational, custody, laboratory or reproduction blockers;
3. replace title-only module-documentation validation with exact source, API, dependency, test and digest binding for every current crate;
4. make stale hand-written Public API tables detectable and regenerate them from candidate source;
5. provide one strict, blocker-specific external completion envelope with complete case/artifact catalogs and a mandatory external cryptographic verifier;
6. ensure templates, owner assertions, self-asserted signature validity, missing negative cases, shared controls, stale/revoked signatures and authority elevation cannot close a blocker;
7. bind all changes to distinct exact-head and prospective-merge pull-request checks;
8. bind the complete current Python validator and plan/platform/Oracle regression surface into the normative manifest so historical-gate repairs cannot drift outside exact-source review.

## 3. V1.4.6 post-merge closure

The V1.4.6 head `{SOURCE_HEAD}` and prospective merge `{BASELINE_COMMIT}` passed the V1.4.6, inherited V1.4.5 and V1.4.4 gates. A current GitHub review approved the exact head, and GitHub created a valid signed two-parent merge with tree `{BASELINE_TREE}`. The post-merge receipt records those immutable facts and closes only the ten repository blockers. `HB-BLK-EXT-001` remains open because a GitHub approval does not establish the complete accountable role registry or signed role receipts.

## 4. Module source truth

The V2 renderer derives the workspace package set, Cargo manifest hashes, Rust source hashes, workspace-internal dependency declarations, public lexical declarations and discovered test functions. It rewrites the Public API section of each guide and adds a generated facts block. Check mode recomputes every fact and rejects source/documentation drift. The V1.4.7 normative manifest also hashes every current Python script and every plan, platform and Oracle regression file executed by the current gate.

The parser is intentionally bounded and lexical. It does not claim Rust name resolution or semantic compatibility. That limitation is part of the normative output rather than an implicit weakness.

## 5. External completion admission

`HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` each receive an `UNEXECUTED` template. The validator can inspect planning shape without closure, but closure mode first enforces the strict JSON schema and independently supplied head/tree/base/two-parent-merge/plan/manifest identities. It then requires the complete blocker-specific case and artifact-kind catalogs, distinct accountable roles, explicit primary-versus-external control separation, no unresolved Critical/High/Unclassified finding, and one domain-separated payload signature from every required role. Signature validity is never accepted from an envelope field: a caller-supplied external verifier must validate cryptography, key role and scope, trust-root state, transparency inclusion and revocation state.

Repository automation cannot populate real identities, legal authority, operating coverage, HSM custody, restricted raw Oracle evidence, independent power-cut control or separately controlled reproduction. Those facts remain open until external operators submit authentic evidence.

## 6. New repository blockers

- `HB-BLK-REPO-059`: V1.4.6 post-merge repository closure was not canonicalized.
- `HB-BLK-REPO-060`: module guides were structurally present but not source/API/dependency/test bound.
- `HB-BLK-REPO-061`: external completion inputs lacked one strict fail-closed admission envelope.
- `HB-BLK-REPO-062`: current entry points and inherited current-plan validation could become stale or reject valid successor revisions.

All four are implemented in source by this candidate and remain review-required until exact-head and prospective-merge CI pass and an independent reviewer accepts the final candidate.

## 7. Required gates

```text
python scripts/render_plan_v1_4_7.py --check
python scripts/validate_plan_v1_4_7.py
python -m unittest discover -s tests/plan -p 'test_*v1_4_7.py' -v
python -m unittest discover -s tests/plan -p 'test_external_completion_evidence_v1.py' -v
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python scripts/validate_plan_v1_4_6.py
python scripts/validate_plan_v1_4_5.py
python scripts/validate_module_documentation_v1_4_4.py
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```

## 8. Carried product work

The production composition root, policy, identity, token, lease, namespace, system and plugin domains, production KMS/HSM, remote rollback provider, qualified recovery target, non-Linux qualification, backup/restore operations, Raft HA, migration, complete OpenBao compatibility and CLI/Agent/Proxy remain product work. This tranche makes their evidence boundaries harder to overclaim; it does not label unimplemented products complete.

## 9. Completion rule

`HB-BLK-REPO-059..062` close only after final source and prospective merge pass the V1.4.7 and inherited gates and receive a current independent review. `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open until authentic completion envelopes pass strict admission. Qualification, compatibility, provider selection and all production/migration/release authority remain false.
'''
    ).lstrip()


def status_document() -> dict[str, Any]:
    return {
        "schema": "heptabao.v1-4-7-post-merge-truth-status.v1",
        "plan_id": PLAN_ID,
        "revision": "1.4.7",
        "status": "SOURCE_IMPLEMENTED_EXACT_HEAD_MERGE_AND_INDEPENDENT_REVIEW_REQUIRED",
        "current_plan": "docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md",
        "current_blocker_register": "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml",
        "normative_manifest": MANIFEST_PATH.as_posix(),
        "current_documentation": "docs/CURRENT_DOCUMENTATION.md",
        "source_baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE},
        "closed_repository_scope_carried_forward": [f"HB-BLK-REPO-{index:03d}" for index in range(49, 59)],
        "implementation": {
            "post_merge_v146_closure_receipt": "IMPLEMENTED_SOURCE",
            "module_documentation_standard_v2": "IMPLEMENTED_SOURCE",
            "module_source_hash_dependency_api_test_truth": "IMPLEMENTED_SOURCE",
            "generated_public_api_sections": "IMPLEMENTED_SOURCE",
            "external_completion_schema_and_admission": "IMPLEMENTED_SOURCE",
            "blocker_specific_negative_tests": "IMPLEMENTED_SOURCE",
            "current_documentation_supersession": "IMPLEMENTED_SOURCE",
            "exact_head_and_prospective_merge_gate": "IMPLEMENTED_SOURCE",
            "complete_python_regression_surface_manifest": "IMPLEMENTED_SOURCE",
        },
        "repository_open": [f"HB-BLK-REPO-{index:03d}" for index in range(59, 63)],
        "external_open": ["HB-BLK-CTRL-001"] + [f"HB-BLK-EXT-{index:03d}" for index in range(1, 8)],
        "product_gaps_carried_forward": [
            "production composition root and mandatory end-to-end request path",
            "policy identity token lease namespace system and plugin domains",
            "production KMS or HSM custody rotation and revocation ceremony",
            "remote append-only rollback anchor and publication-fence provider",
            "qualified recovery target with atomic empty admission and readback",
            "non-Linux adapters and filesystem or storage-controller qualification",
            "retention compaction offsite backup custody and restore drills",
            "Raft HA replication membership snapshots and standby reconciliation",
            "online migration upgrade downgrade and mixed-version operation",
            "full OpenBao compatibility and Oracle-derived implementation",
            "CLI Agent Proxy and production operations surface",
        ],
        "claims": CLAIMS,
    }


def blocker_register() -> dict[str, Any]:
    added = [
        {
            "id": "HB-BLK-REPO-059",
            "class": "REPOSITORY_CONTROLLED",
            "severity": "HIGH",
            "title": "V1.4.6 post-merge repository closure was not canonicalized",
            "state": "IMPLEMENTED_SOURCE_REVIEW_REQUIRED",
            "closure_criteria": [
                "receipt binds exact reviewed head base merge parent graph and merge tree",
                "repository blockers 049 through 058 close without closing control or external blockers",
                "authority flags remain false",
            ],
            "evidence": ["planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml"],
            "closure_receipt_required": True,
        },
        {
            "id": "HB-BLK-REPO-060",
            "class": "REPOSITORY_CONTROLLED",
            "severity": "HIGH",
            "title": "module documentation was structurally complete but not source truth bound",
            "state": "IMPLEMENTED_SOURCE_REVIEW_REQUIRED",
            "closure_criteria": [
                "every workspace crate maps to exactly one module guide",
                "Cargo and Rust source hashes internal dependencies public lexical declarations and tests are recomputed",
                "generated Public API and facts blocks reject drift and hand edits",
                "bounded lexical scope and nonclaims remain explicit",
            ],
            "evidence": [
                "docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md",
                TRUTH_PATH.as_posix(),
                "scripts/render_plan_v1_4_7.py",
                "tests/plan/test_module_source_truth_v1_4_7.py",
            ],
            "closure_receipt_required": True,
        },
        {
            "id": "HB-BLK-REPO-061",
            "class": "REPOSITORY_CONTROLLED",
            "severity": "CRITICAL",
            "title": "external completion evidence lacked one strict fail-closed admission gate",
            "state": "IMPLEMENTED_SOURCE_REVIEW_REQUIRED",
            "closure_criteria": [
                "one schema covers control and external blocker completion envelopes",
                "closure mode binds exact source and merge identities",
                "schema validation exact merge parents complete blocker-specific cases and artifact kinds fail closed",
                "every required role signs a domain-separated payload verified by an external cryptographic verifier",
                "separation roots findings freshness transparency revocation and authority flags fail closed",
                "UNEXECUTED templates cannot be admitted as closure",
            ],
            "evidence": [
                "schemas/heptabao_external_completion_evidence_v1.schema.json",
                "scripts/validate_external_completion_evidence_v1.py",
                "tests/plan/test_external_completion_evidence_v1.py",
                "qualifications/external/templates",
            ],
            "closure_receipt_required": True,
        },
        {
            "id": "HB-BLK-REPO-062",
            "class": "REPOSITORY_CONTROLLED",
            "severity": "MEDIUM",
            "title": "current entry points and inherited plan-marker validation could become stale or reject successors",
            "state": "IMPLEMENTED_SOURCE_REVIEW_REQUIRED",
            "closure_criteria": [
                "README and the single current portal select V1.4.7 plan status blocker register and manifest",
                "inherited validators accept a well-formed versioned successor marker without accepting an unversioned latest alias",
                "V1.4.6 remains immutable inherited evidence",
                "the full historical plan, platform and Oracle regression surfaces execute in the current gate and are digest-bound by the V1.4.7 manifest",
                "external authority boundary remains explicit",
            ],
            "evidence": [
                "README.md",
                "docs/CURRENT_DOCUMENTATION.md",
                "scripts/validate_plan_v1_2.py",
                "tests/plan/test_plan_v1_2.py",
                "scripts/validate_plan_v1_2_1.py",
                "tests/plan/test_plan_v1_2_1.py",
                "scripts/validate_plan_v1_3.py",
                "tests/plan/test_plan_v1_3.py",
                "scripts/validate_plan_v1_3_1.py",
                "tests/plan/test_plan_v1_3_1.py",
                "scripts/validate_plan_v1_4.py",
                "tests/plan/test_plan_v1_4.py",
                "scripts/validate_plan_v1_4_1.py",
                "tests/plan/test_plan_v1_4_1.py",
                "scripts/validate_plan_v1_4_2.py",
                "tests/plan/test_plan_v1_4_2.py",
                "scripts",
                "tests/plan",
                "tests/platform",
                "tests/oracle",
                ".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml",
            ],
            "closure_receipt_required": True,
        },
    ]
    return {
        "schema": "heptabao.blocker-register-extension.v1_4_7",
        "plan_id": PLAN_ID,
        "revision": "1.4.7",
        "status": "ACTIVE_FAIL_CLOSED",
        "inherits": "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_6.yaml",
        "source_baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE},
        "closed_carried_forward": [
            {"id": f"HB-BLK-REPO-{index:03d}", "state": "CLOSED_REPOSITORY_SCOPE", "receipt": "planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml"}
            for index in range(49, 59)
        ],
        "added_blockers": added,
        "external_and_control_blockers_carried_forward": ["HB-BLK-CTRL-001"] + [f"HB-BLK-EXT-{index:03d}" for index in range(1, 8)],
        "product_gaps_carried_forward": status_document()["product_gaps_carried_forward"],
        "claims": CLAIMS,
    }


def post_merge_receipt() -> dict[str, Any]:
    return {
        "schema": "heptabao.repository-post-merge-closure-receipt.v1",
        "plan_id": PLAN_ID,
        "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY_FULL_NAME},
        "pull_request": 60,
        "base_commit": BASE_COMMIT,
        "reviewed_head_commit": SOURCE_HEAD,
        "reviewed_head_tree": SOURCE_TREE,
        "merge_commit": BASELINE_COMMIT,
        "merge_tree": BASELINE_TREE,
        "merge_parents": [BASE_COMMIT, SOURCE_HEAD],
        "merge_verification": {"provider": "GitHub", "verified": True, "reason": "valid"},
        "required_runs": [
            {"id": 33575576171, "name": "HeptaBao V1.4.6 authoritative recovery closure", "result": "PASS"},
            {"id": 33575576185, "name": "plan-v1.4.5-security-invariant-closure", "result": "PASS"},
            {"id": 33575576180, "name": "plan-v1.4.4-module-documentation", "result": "PASS"},
        ],
        "current_head_review": {
            "review_id": 5084963097,
            "reviewer_login": "Franksudoman",
            "reviewer_stable_account_id": 273670192,
            "state": "APPROVED",
            "commit": SOURCE_HEAD,
            "submitted_at": "2026-09-02T02:22:50Z",
            "scope_effect": "GITHUB_REPOSITORY_CHANGE_ACCEPTANCE_ONLY",
            "accountable_role_receipt": False,
        },
        "closed_repository_blockers": [f"HB-BLK-REPO-{index:03d}" for index in range(49, 59)],
        "external_or_control_blockers_closed": [],
        "limitations": [
            "GitHub approval does not establish the complete accountable role registry",
            "GitHub merge signature is not the isolated project signing trust root",
            "repository CI does not establish legal operational Oracle laboratory or independent reproduction facts",
        ],
        "claims": CLAIMS,
    }


def admission_catalog() -> dict[str, Any]:
    return {
        "schema": "heptabao.external-completion-admission-catalog.v1",
        "plan_id": PLAN_ID,
        "envelope_schema": "schemas/heptabao_external_completion_evidence_v1.schema.json",
        "validator": "scripts/validate_external_completion_evidence_v1.py",
        "protocol": "docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md",
        "closure_mode": "FAIL_CLOSED_EXACT_SOURCE_AND_EXTERNAL_CRYPTOGRAPHIC_VERIFIER_REQUIRED",
        "required_case_catalog": "embedded-in-validator",
        "required_artifact_kind_catalog": "embedded-in-validator",
        "signature_policy": "domain-separated-payload-external-verifier-only",
        "blockers": [
            {
                "id": blocker,
                "template": f"qualifications/external/templates/{blocker}.template.json",
                "state": "OPEN_EXTERNAL_EXECUTION_REQUIRED",
            }
            for blocker in ["HB-BLK-CTRL-001"] + [f"HB-BLK-EXT-{index:03d}" for index in range(1, 8)]
        ],
        "claims": CLAIMS,
    }

def template(blocker: str) -> dict[str, Any]:
    return {
        "schema": "heptabao.external-completion-evidence.v1",
        "blocker_id": blocker,
        "state": "UNEXECUTED",
        "repository": {"id": REPOSITORY_ID, "full_name": REPOSITORY_FULL_NAME},
        "source": {
            "commit": None,
            "tree": None,
            "base_commit": None,
            "merge_commit": None,
            "merge_tree": None,
            "merge_parent_one": None,
            "merge_parent_two": None,
            "plan_digest": None,
            "manifest_digest": None,
        },
        "scope": [],
        "actors": [],
        "separation": {},
        "checks": [{"case_id": "UNEXECUTED", "status": "UNEXECUTED", "evidence_digest": None}],
        "artifacts": [],
        "findings": [],
        "signatures": [],
        "claims": CLAIMS,
    }

def qualifications_readme() -> str:
    return textwrap.dedent(
        '''# External completion evidence

This directory contains only fail-closed input templates for `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007`.

Every committed template is `UNEXECUTED` and non-authoritative. It is not evidence that an operator, reviewer, legal function, incident team, key custodian, Oracle lane, storage laboratory or reproduction environment exists. A populated candidate must be held under the declared custody system and admitted with independently supplied exact source identities, the complete mandatory case/artifact catalogs, and an external cryptographic verifier through `scripts/validate_external_completion_evidence_v1.py --require-closure`.

Do not commit restricted raw Oracle captures, private vulnerability details, production credentials, private signing keys or destructive-laboratory secrets here. Commit only an approved sanitized object or immutable restricted reference.
'''
    ).lstrip()


def static_files() -> dict[Path, str]:
    values: dict[Path, str] = {
        Path("README.md"): current_readme(),
        Path("docs/CURRENT_DOCUMENTATION.md"): current_documentation(),
        Path("docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md"): module_standard_v2(),
        Path("docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md"): external_protocol(),
        Path("docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md"): plan_document(),
        Path("planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml"): dump_yaml(status_document()),
        Path("planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml"): dump_yaml(blocker_register()),
        Path("planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml"): dump_yaml(admission_catalog()),
        Path("planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml"): dump_yaml(post_merge_receipt()),
        Path("schemas/heptabao_external_completion_evidence_v1.schema.json"): json.dumps(external_schema(), indent=2, sort_keys=True) + "\n",
        Path("scripts/validate_external_completion_evidence_v1.py"): external_validator_source(),
        Path("scripts/validate_plan_v1_4_7.py"): plan_validator_source(),
        Path("tests/plan/test_external_completion_evidence_v1.py"): external_test_source(),
        Path("tests/plan/test_module_source_truth_v1_4_7.py"): module_test_source(),
        Path("tests/plan/test_plan_v1_4_7.py"): plan_test_source(),
        Path(".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml"): workflow_source(),
        Path("qualifications/external/README.md"): qualifications_readme(),
    }
    for blocker in ["HB-BLK-CTRL-001"] + [f"HB-BLK-EXT-{index:03d}" for index in range(1, 8)]:
        values[Path(f"qualifications/external/templates/{blocker}.template.json")] = json.dumps(
            template(blocker), indent=2, sort_keys=True
        ) + "\n"
    return values


def normative_paths(truth: dict[str, Any]) -> list[Path]:
    paths = [
        Path("README.md"),
        Path("docs/CURRENT_DOCUMENTATION.md"),
        Path("docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md"),
        Path("planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml"),
        Path("planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml"),
        TRUTH_PATH,
        Path("planning/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_V1.yaml"),
        Path("planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml"),
        Path("docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md"),
        Path("docs/modules/README.md"),
        Path("docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md"),
        Path("schemas/heptabao_external_completion_evidence_v1.schema.json"),
        Path("scripts/render_plan_v1_4_7.py"),
        Path("scripts/validate_plan_v1_4_7.py"),
        Path("scripts/validate_external_completion_evidence_v1.py"),
        Path(".github/workflows/plan-v1.4.7-post-merge-truth-and-external-admission.yml"),
    ]
    paths.append(Path("qualifications/external/README.md"))
    paths.extend(Path(module["module_guide"]) for module in truth["modules"])
    paths.extend(sorted(Path("qualifications/external/templates").glob("*.json")))
    paths.extend(sorted(Path("scripts").glob("*.py")))
    paths.extend(sorted(Path("tests/plan").glob("test_*.py")))
    paths.extend(sorted(Path("tests/platform").glob("test_*.py")))
    paths.extend(sorted(Path("tests/oracle").glob("test_*.py")))
    return sorted(set(paths), key=lambda item: item.as_posix())


def write_or_compare(root: Path, values: dict[Path, str], *, write: bool) -> None:
    mismatches: list[str] = []
    for relative, content in sorted(values.items(), key=lambda item: item[0].as_posix()):
        path = root / relative
        if write:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        elif not path.is_file() or path.read_text(encoding="utf-8") != content:
            mismatches.append(relative.as_posix())
    if mismatches:
        raise SystemExit(f"generated V1.4.7 content drift: {mismatches}")


def render(root: Path, *, write: bool) -> None:
    values = static_files()
    write_or_compare(root, values, write=write)
    truth = build_truth(root)
    truth_text = dump_yaml(truth)
    write_or_compare(root, {TRUTH_PATH: truth_text}, write=write)
    doc_values = {
        Path(module["module_guide"]): module_doc_expected(root, module) for module in truth["modules"]
    }
    doc_values[Path("docs/modules/README.md")] = module_index_expected(root, truth)
    write_or_compare(root, doc_values, write=write)
    # Rebuild truth after generated documentation. Source facts are intentionally unaffected.
    truth = build_truth(root)
    write_or_compare(root, {TRUTH_PATH: dump_yaml(truth)}, write=write)
    manifest_files = []
    for relative in normative_paths(truth):
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"normative file missing: {relative}")
        manifest_files.append({"path": relative.as_posix(), "sha256": sha256_file(path)})
    manifest = {
        "schema": "heptabao.normative-document-manifest.v1_4_7",
        "plan_id": PLAN_ID,
        "revision": "1.4.7",
        "status": "CANDIDATE_EXACT_HEAD_AND_MERGE_REVIEW_REQUIRED",
        "source_baseline": {"commit": BASELINE_COMMIT, "tree": BASELINE_TREE},
        "files": manifest_files,
        "claims": CLAIMS,
    }
    write_or_compare(root, {MANIFEST_PATH: dump_yaml(manifest)}, write=write)


def main() -> int:
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true")
    group.add_argument("--check", action="store_true")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    render(root, write=args.write)
    print(f"PASS V1.4.7 render mode={'write' if args.write else 'check'} root={root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
