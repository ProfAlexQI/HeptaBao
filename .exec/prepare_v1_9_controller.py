#!/usr/bin/env python3
"""Create an execution copy of the V1.9 controller with bound repairs.

The committed controller remains the immutable forensic input.  This helper
applies only exact-count substitutions to its execution copy:

* make the V1.7 materializer filename match the V3 asset patch contract;
* patch the two source-bound defects in the generated V1.9 workflow.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

GENERATOR_CHECK = 'python -m py_compile "$WORK/converge_v1_9.py" "$WORK/augment_external_v2.py"'
GENERATOR_INSERT = (
    'python .exec/patch_v1_9_generator.py "$WORK/converge_v1_9.py"\n'
    + GENERATOR_CHECK
)
V170_OLD = '$WORK/v170/materialize.py'
V170_NEW = '$WORK/v170/materialize_v1_7_0.py'
V170_REFERENCE_COUNT = 3


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    source = args.source.read_text(encoding="utf-8")
    if source.count(GENERATOR_CHECK) != 1:
        raise SystemExit(
            "controller generator insertion point count is "
            f"{source.count(GENERATOR_CHECK)}, expected 1"
        )
    if "patch_v1_9_generator.py" in source:
        raise SystemExit("committed controller already contains an unexpected generator patch")
    if source.count(V170_OLD) != V170_REFERENCE_COUNT:
        raise SystemExit(
            f"V1.7 materializer reference count is {source.count(V170_OLD)}, "
            f"expected {V170_REFERENCE_COUNT}"
        )
    if V170_NEW in source:
        raise SystemExit("committed controller unexpectedly already uses the repaired V1.7 path")

    prepared = source.replace(V170_OLD, V170_NEW)
    prepared = prepared.replace(GENERATOR_CHECK, GENERATOR_INSERT)
    if prepared.count(V170_NEW) != V170_REFERENCE_COUNT or V170_OLD in prepared:
        raise SystemExit("V1.7 materializer path repair was incomplete")

    args.output.write_text(prepared, encoding="utf-8")
    args.output.chmod(0o700)
    print(
        "PASS prepared V1.9 controller "
        f"source_sha256={sha256(source)} "
        f"prepared_sha256={sha256(prepared)} "
        f"v170_path_repairs={V170_REFERENCE_COUNT}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
