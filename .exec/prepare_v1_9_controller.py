#!/usr/bin/env python3
"""Prepare the V1.9 controller and bind the V1.4.7 generator repair.

The prior, reviewed controller-preparation source is read from one immutable Git
commit and verified by Git blob identity. This wrapper then adds exactly two
commands to the generated execution copy: archive the repair helper before the
checkout moves, and execute it on the exact V1.4.7 source before historical
validation. No validator or authority condition is weakened.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from pathlib import Path

PINNED_PREPARE_COMMIT = "5253f4a538a3acb8e7154662820398ca7de8359e"
PINNED_PREPARE_BLOB = "a3df98e886959e42286bc107dc77345bef9e59cf"
COPY_ANCHOR = (
    'cp .exec/validate_inherited_stages_for_v1_9.py '
    '"$WORK/validate_inherited_stages_for_v1_9.py"'
)
COPY_COMMAND = (
    'cp .exec/repair_v1_4_7_source_for_convergence.py '
    '"$WORK/repair_v1_4_7_source_for_convergence.py"'
)
COPY_INSERT = COPY_ANCHOR + "\n" + COPY_COMMAND
VALIDATION_ANCHOR = (
    "# Execute the complete inherited plan suite while the exact V1.4.7 source is"
)
VALIDATION_COMMAND = 'python "$WORK/repair_v1_4_7_source_for_convergence.py"'
VALIDATION_INSERT = VALIDATION_COMMAND + "\n\n" + VALIDATION_ANCHOR


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()


def replace_exact(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label} count is {count}, expected 1")
    return text.replace(old, new, 1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    original = subprocess.check_output(
        [
            "git",
            "show",
            f"{PINNED_PREPARE_COMMIT}:.exec/prepare_v1_9_controller.py",
        ]
    )
    observed_blob = git_blob_sha(original)
    if observed_blob != PINNED_PREPARE_BLOB:
        raise SystemExit(
            f"pinned prepare-controller blob mismatch: {observed_blob}"
        )

    temporary = args.output.parent / f".prepare-v1-9-original-{os.getpid()}.py"
    try:
        temporary.write_bytes(original)
        subprocess.run(
            [sys.executable, str(temporary), str(args.source), str(args.output)],
            check=True,
        )
    finally:
        temporary.unlink(missing_ok=True)

    prepared = args.output.read_text(encoding="utf-8")
    if "repair_v1_4_7_source_for_convergence.py" in prepared:
        raise SystemExit("prepared controller unexpectedly already contains V1.4.7 repair")
    prepared = replace_exact(
        prepared, COPY_ANCHOR, COPY_INSERT, "V1.4.7 helper archive anchor"
    )
    prepared = replace_exact(
        prepared,
        VALIDATION_ANCHOR,
        VALIDATION_INSERT,
        "V1.4.7 pre-validation repair anchor",
    )
    if prepared.count(COPY_COMMAND) != 1:
        raise SystemExit("prepared controller V1.4.7 helper archive command is incomplete")
    if prepared.count(VALIDATION_COMMAND) != 1:
        raise SystemExit("prepared controller V1.4.7 repair execution command is incomplete")
    if prepared.count("repair_v1_4_7_source_for_convergence.py") != 3:
        raise SystemExit("prepared controller V1.4.7 repair path references are incomplete")

    args.output.write_text(prepared, encoding="utf-8")
    args.output.chmod(0o700)
    print(
        "PASS augmented prepared V1.9 controller with source-bound V1.4.7 repair "
        f"prepared_sha256={hashlib.sha256(prepared.encode()).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
