#!/usr/bin/env python3
"""Normalize exact closure patch programs after runner diagnostics."""

from __future__ import annotations

import sys
from pathlib import Path

if len(sys.argv) != 4:
    raise SystemExit("usage: normalize_patch_programs.py PATCH DELTA GATE_DELTA")

patch_path = Path(sys.argv[1])
delta_path = Path(sys.argv[2])
gate_path = Path(sys.argv[3])

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

status_path = "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml"
delta = delta_path.read_text(encoding="utf-8")
for old, new, label in (
    (
        '''  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension:
''',
        f'''  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension: {status_path}
''',
        "e3f delta input status",
    ),
    (
        '''  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension:
''',
        f'''  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension: {status_path}
''',
        "e3f delta output status",
    ),
):
    if delta.count(old) != 1:
        raise SystemExit(f"{label} normalization marker drift")
    delta = delta.replace(old, new, 1)
delta_path.write_text(delta, encoding="utf-8")

gate = gate_path.read_text(encoding="utf-8")
for old, new, label in (
    (
        '''  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension:
''',
        f'''  bounded_state_admission_and_fresh_dispatch_time: IMPLEMENTED_SOURCE
blocker_extension: {status_path}
''',
        "gate delta input status",
    ),
    (
        '''  secret_debug_derive_negative_gate: IMPLEMENTED_SOURCE
blocker_extension:
''',
        f'''  secret_debug_derive_negative_gate: IMPLEMENTED_SOURCE
blocker_extension: {status_path}
''',
        "gate delta output status",
    ),
):
    if gate.count(old) != 1:
        raise SystemExit(f"{label} normalization marker drift")
    gate = gate.replace(old, new, 1)
gate_path.write_text(gate, encoding="utf-8")

print("closure patch programs normalized from execution diagnostics")
