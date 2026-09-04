#!/usr/bin/env python3
"""Narrow the exact V1.8 patch target to the service test module.

The pinned V1.8 patch script searched for a generic BTreeSet test-module prefix
that occurs in both `heptabao-service` and `heptabao-agent-proxy`.  This patch
changes only that one patch-table entry so the AtomicU64 import is added beside
the unique control-plane import in the service module.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

OLD = """    ('#[cfg(test)]mod tests{use std::collections::BTreeSet;use super::*;', '#[cfg(test)]mod tests{use std::collections::BTreeSet;use std::sync::atomic::{AtomicU64,Ordering};use super::*;'),"""
NEW = """    ('#[cfg(test)]mod tests{use std::collections::BTreeSet;use super::*;use heptabao_control_plane', '#[cfg(test)]mod tests{use std::collections::BTreeSet;use std::sync::atomic::{AtomicU64,Ordering};use super::*;use heptabao_control_plane'),"""


def sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    raw = args.path.read_bytes()
    text = raw.decode("utf-8")
    if text.count(OLD) != 1:
        raise SystemExit(f"V1.8 patch-table target count is {text.count(OLD)}, expected 1")
    if NEW in text:
        raise SystemExit("V1.8 patch script unexpectedly already contains the narrowed target")
    patched = text.replace(OLD, NEW)
    compile(patched, str(args.path), "exec")
    args.path.write_text(patched, encoding="utf-8")
    print(
        "PASS narrowed V1.8 service-test patch target "
        f"source_sha256={sha256(raw)} patched_sha256={sha256(patched.encode())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
