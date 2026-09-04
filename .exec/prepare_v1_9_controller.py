#!/usr/bin/env python3
"""Create an execution copy of the V1.9 controller with the bound generator patch."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

NEEDLE = 'python -m py_compile "$WORK/converge_v1_9.py" "$WORK/augment_external_v2.py"'
INSERT = (
    'python .exec/patch_v1_9_generator.py "$WORK/converge_v1_9.py"\n'
    + NEEDLE
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(NEEDLE) != 1:
        raise SystemExit(f"controller insertion point count is {source.count(NEEDLE)}, expected 1")
    if "patch_v1_9_generator.py" in source:
        raise SystemExit("committed controller already contains an unexpected generator patch")
    prepared = source.replace(NEEDLE, INSERT)
    args.output.write_text(prepared, encoding="utf-8")
    args.output.chmod(0o700)
    print(
        "PASS prepared V1.9 controller "
        f"source_sha256={hashlib.sha256(source.encode()).hexdigest()} "
        f"prepared_sha256={hashlib.sha256(prepared.encode()).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
