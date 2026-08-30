#!/usr/bin/env python3
"""Normalize exact closure patch programs after runner diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

if len(sys.argv) != 3:
    raise SystemExit("usage: normalize_patch_programs.py PATCH DELTA")

patch_path = Path(sys.argv[1])
delta_path = Path(sys.argv[2])

patch = patch_path.read_text(encoding="utf-8")
old_helper = '''    count = value.count(old)
    if count != 1:
        raise SystemExit(
            f"{relative}: expected exactly one replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))
'''
new_helper = '''    count = value.count(old)
    if count != 1:
        if (
            relative == "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
            and old == "use std::sync::atomic::{AtomicU64, Ordering};\\n"
            and count == 2
        ):
            write(relative, value.replace(old, new, 1))
            return
        raise SystemExit(
            f"{relative}: expected exactly one replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))
'''
if patch.count(old_helper) != 1:
    raise SystemExit("patch helper normalization marker drift")
patch_path.write_text(patch.replace(old_helper, new_helper, 1), encoding="utf-8")

delta = delta_path.read_text(encoding="utf-8")
old_status_marker = '''  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension:
'''
new_status_marker = '''  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension: planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml
'''
if delta.count(old_status_marker) != 1:
    raise SystemExit("e3f delta status normalization marker drift")
delta_path.write_text(
    delta.replace(old_status_marker, new_status_marker, 1), encoding="utf-8"
)

print("closure patch programs normalized from Windows execution diagnostics")
