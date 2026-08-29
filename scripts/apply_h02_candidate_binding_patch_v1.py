#!/usr/bin/env python3
"""Apply the H02 candidate/support direct-dependency binding repair.

Temporary maintenance helper.  The invoking workflow removes this file after the
repaired source and its tests pass.  Every edit is anchored and fail-closed.
"""
from __future__ import annotations

from pathlib import Path

HARNESS = Path("scripts/h02_candidate_adapter_harness_v1.py")
PLAN = Path("planning/HEPTABAO_H02_CANDIDATE_ADAPTERS_V1.yaml")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    observed = text.count(old)
    if observed != 1:
        raise SystemExit(f"{label} anchor drift: expected=1 observed={observed}")
    return text.replace(old, new, 1)


def patch_harness() -> None:
    text = HARNESS.read_text(encoding="utf-8")
    text = replace_once(
        text,
        'HARNESS_VERSION = "1.0.0"',
        'HARNESS_VERSION = "1.1.0"',
        "harness-version",
    )
    profiles = [
        (
            '        "manifest": "probes/h02/tokio-minimal/Cargo.toml",\n        "adapter_scope":',
            '        "manifest": "probes/h02/tokio-minimal/Cargo.toml",\n'
            '        "candidate_package": "tokio",\n'
            '        "support_dependencies": [],\n'
            '        "adapter_scope":',
            "tokio-profile",
        ),
        (
            '        "manifest": "probes/h02/rustls-ring/Cargo.toml",\n        "adapter_scope":',
            '        "manifest": "probes/h02/rustls-ring/Cargo.toml",\n'
            '        "candidate_package": "rustls",\n'
            '        "support_dependencies": ["zeroize"],\n'
            '        "adapter_scope":',
            "rustls-ring-profile",
        ),
        (
            '        "manifest": "probes/h02/rustls-aws-lc/Cargo.toml",\n        "adapter_scope":',
            '        "manifest": "probes/h02/rustls-aws-lc/Cargo.toml",\n'
            '        "candidate_package": "rustls",\n'
            '        "support_dependencies": ["jobserver", "zeroize"],\n'
            '        "adapter_scope":',
            "rustls-aws-lc-profile",
        ),
        (
            '        "manifest": "probes/h02/openraft-tokio/Cargo.toml",\n        "adapter_scope":',
            '        "manifest": "probes/h02/openraft-tokio/Cargo.toml",\n'
            '        "candidate_package": "openraft",\n'
            '        "support_dependencies": ["openraft-memstore", "serde_json", "tokio", "validit"],\n'
            '        "adapter_scope":',
            "openraft-profile",
        ),
    ]
    for old, new, label in profiles:
        text = replace_once(text, old, new, label)

    start = text.index("def manifest_binding(")
    end = text.index("\n\ndef _blocked_rows", start)
    replacement = '''def _direct_dependency_binding(path: Path, package: str, spec: Any) -> dict[str, Any]:
    if isinstance(spec, str):
        version = spec
        default_features = True
        features: list[str] = []
    elif isinstance(spec, dict):
        allowed_keys = {"version", "default-features", "features"}
        unexpected_keys = sorted(set(spec) - allowed_keys)
        if unexpected_keys:
            raise Failure(
                f"{path}: dependency {package!r} has unapproved keys: {unexpected_keys!r}"
            )
        version = str(spec.get("version", ""))
        default_features = bool(spec.get("default-features", True))
        raw_features = spec.get("features", [])
        if not isinstance(raw_features, list):
            raise Failure(f"{path}: dependency {package!r} features must be a list")
        features = sorted(str(item) for item in raw_features)
        if len(features) != len(set(features)):
            raise Failure(f"{path}: dependency {package!r} has duplicate features")
    else:
        raise Failure(
            f"{path}: dependency {package!r} must be a version string or inline table"
        )
    if not version.startswith("=") or len(version) <= 1:
        raise Failure(f"{path}: dependency {package!r} must use an exact =version pin")
    return {
        "package": package,
        "version": version,
        "default_features": default_features,
        "features": features,
    }


def manifest_binding(
    root: Path,
    profile: dict[str, Any],
    toolchain: str,
    target: str,
) -> dict[str, Any]:
    path = root / profile["manifest"]
    document = tomllib.loads(path.read_text(encoding="utf-8"))
    dependencies = document.get("dependencies", {})
    if not isinstance(dependencies, dict) or not dependencies:
        raise Failure(f"{path}: direct dependency table is missing or empty")
    for table_name in ("dev-dependencies", "build-dependencies"):
        table = document.get(table_name, {})
        if table:
            raise Failure(f"{path}: unbound {table_name} table is forbidden")
    if document.get("target"):
        raise Failure(f"{path}: unbound target-specific dependency tables are forbidden")

    candidate_package = str(profile["candidate_package"])
    support_dependencies = sorted(
        str(item) for item in profile.get("support_dependencies", [])
    )
    if candidate_package in support_dependencies:
        raise Failure(f"{path}: candidate dependency cannot also be a support dependency")
    if len(support_dependencies) != len(set(support_dependencies)):
        raise Failure(f"{path}: duplicate support dependency declaration")

    expected_packages = {candidate_package, *support_dependencies}
    actual_packages = set(dependencies)
    if actual_packages != expected_packages:
        missing = sorted(expected_packages - actual_packages)
        unexpected = sorted(actual_packages - expected_packages)
        raise Failure(
            f"{path}: direct dependency drift: missing={missing!r} "
            f"unexpected={unexpected!r}"
        )

    dependency_profile = {
        package: _direct_dependency_binding(path, package, dependencies[package])
        for package in sorted(actual_packages)
    }
    candidate = dependency_profile[candidate_package]
    if candidate["version"] != f"={profile['version']}":
        raise Failure(f"{path}: candidate version drift: {candidate['version']!r}")

    binding = {
        "profile_id": profile["profile_id"],
        "candidate_id": profile["candidate_id"],
        "package": candidate_package,
        "version": profile["version"],
        "manifest_path": profile["manifest"],
        "manifest_sha256": file_sha256(path),
        "default_features": candidate["default_features"],
        "features": candidate["features"],
        "support_dependencies": support_dependencies,
        "direct_dependencies": dependency_profile,
        "toolchain": toolchain,
        "target": target,
    }
    binding["feature_profile_sha256"] = sha256(binding)
    return binding
'''
    if "expected exactly one candidate dependency" not in text[start:end]:
        raise SystemExit("legacy manifest-binding failure anchor is absent")
    text = text[:start] + replacement + text[end:]
    if "expected exactly one candidate dependency" in text:
        raise SystemExit("legacy single-dependency assumption remains")
    HARNESS.write_text(text, encoding="utf-8", newline="\n")


def patch_plan() -> None:
    text = PLAN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "  - The feature_profile_sha256 includes the exact manifest, features, toolchain and target; it is not reusable across another toolchain.",
        "  - The feature_profile_sha256 includes the exact manifest, candidate features, complete allowlisted direct-dependency profile, toolchain and target; it is not reusable across dependency, feature, toolchain or target drift.",
        "candidate-plan-binding-rule",
    )
    PLAN.write_text(text, encoding="utf-8", newline="\n")


def main() -> int:
    patch_harness()
    patch_plan()
    print("H02 candidate/support dependency binding patch applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
