#!/usr/bin/env python3
"""Apply source-bound repairs required by the V1.9 candidate and PR gate."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ORIGINAL_SHA256 = "ab838212f426b8f526e27a1e0e6981a97bfacbf7c9b48772594d4aee66faa838"
PATCHED_SHA256 = "5c7ca32059c02babbc5352dec351b71a64c302584d33a4d7c6bbc12d2c6f78d0"
REPLACEMENTS = (
    ("github.event.pul_request.base.sha", "github.event.pull_request.base.sha", 1),
    ('test -zi "${extra:-}"', 'test -z "${extra:-}"', 1),
    (
        "python -m unittest discover -s tests/plan -p 'test_plan_v1_9_0.py' -v",
        "python -m unittest discover -s tests/plan -p 'test_*.py' -v",
        2,
    ),
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    raw = args.path.read_bytes()
    observed = digest(raw)
    if observed != ORIGINAL_SHA256:
        raise SystemExit(f"unexpected V1.9 generator source: {observed}")
    text = raw.decode("utf-8")
    for old, new, expected_count in REPLACEMENTS:
        count = text.count(old)
        if count != expected_count:
            raise SystemExit(
                f"generator repair target {old!r}: observed {count}, expected {expected_count}"
            )
        text = text.replace(old, new)
    patched = text.encode("utf-8")
    observed_patched = digest(patched)
    if observed_patched != PATCHED_SHA256:
        raise SystemExit(
            f"patched V1.9 generator digest mismatch: {observed_patched}"
        )
    compile(text, str(args.path), "exec")
    args.path.write_bytes(patched)
    print(
        "PASS patched V1.9 generator "
        f"sha256={PATCHED_SHA256} full_plan_test_surfaces=2"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
