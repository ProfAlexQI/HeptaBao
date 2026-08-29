#!/usr/bin/env python3
"""Apply exact source fixes learned from real candidate Runner evidence."""
from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    observed = text.count(old)
    if observed != 1:
        raise SystemExit(f"{label}: expected one anchor, observed {observed}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8", newline="\n")


def main() -> int:
    replace_once(
        "probes/h02/rustls-public-fixtures.rs",
        "//! Synthetic public X.509 DER fixtures for H02 rustls candidate adapters.\n//! No private key material is present in this file.",
        "// Synthetic public X.509 DER fixtures for H02 rustls candidate adapters.\n// No private key material is present in this file.",
        "rustls-fixture-comment",
    )
    replace_once(
        "probes/h02/openraft-tokio/Cargo.toml",
        'validit = "=0.2.5"',
        'validit = "=0.2.6"',
        "openraft-validit-pin",
    )
    replace_once(
        "tests/platform/test_h02_candidate_adapter_harness_v1.py",
        "'validit': 'validit = \"=0.2.5\"'",
        "'validit': 'validit = \"=0.2.6\"'",
        "test-validit-pin",
    )
    print("H02 candidate compile fixes applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
