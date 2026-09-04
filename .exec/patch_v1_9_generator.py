#!/usr/bin/env python3
"""Apply the two source-bound fixes required by the V1.9 candidate workflow."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

ORIGINAL_SHA256 = "ab838212f426b8f526e27a1e0e6981a97bfacbf7c9b48772594d4aee66faa838"
PATCHED_SHA256 = "1d4f937a91d5db02d35f5651206e27bee0722bc65ba21c1bafdd3830b0e13070"
REPLACEMENTS = (
    ("github.event.pul_request.base.sha", "github.event.pull_request.base.sha"),
    ('test -zi "${extra:-}"', 'test -z "${extra:-}"'),
)


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    raw = args.path.read_bytes()
    if digest(raw) != ORIGINAL_SHA256:
        raise SystemExit(f"unexpected V1.9 generator source: {digest(raw)}")
    text = raw.decode("utf-8")
    for old, new in REPLACEMENTS:
        count = text.count(old)
        if count != 1:
            raise SystemExit(f"expected one generator defect {old!r}, observed {count}")
        text = text.replace(old, new)
    patched = text.encode("utf-8")
    if digest(patched) != PATCHED_SHA256:
        raise SystemExit(f"patched V1.9 generator digest mismatch: {digest(patched)}")
    compile(text, str(args.path), "exec")
    args.path.write_bytes(patched)
    print(f"PASS patched V1.9 generator sha256={PATCHED_SHA256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
