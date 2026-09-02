#!/usr/bin/env python3

from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
required = {
    "http_api.rs",
    "ha_core.rs",
    "plugin_host.rs",
    "compat_runner.rs",
    "client_tools.rs",
}
present = {path.name for path in root.glob("*.rs")}
if present != required:
    raise SystemExit(
        f"V1.7 asset set mismatch: missing={sorted(required - present)} "
        f"extra={sorted(present - required)}"
    )

for path in sorted(root.glob("*.rs")):
    text = path.read_text(encoding="utf-8")
    if "assert!(false);" in text:
        raise SystemExit(f"constant assertion survived V1.7 hardening: {path.name}")

http = (root / "http_api.rs").read_text(encoding="utf-8")
if "trim_matches(|character| matches!(character, ' ' | '\\t'))" not in http:
    raise SystemExit("V1.7 HTTP canonical trim hardening missing")

ha = (root / "ha_core.rs").read_text(encoding="utf-8")
if ha.count("if self.leader_fence.is_some_and(|current| {") != 1:
    raise SystemExit("V1.7 leader-fence hardening missing or duplicated")
if ha.count("snapshot.applied_index == self.applied_index") != 1:
    raise SystemExit("V1.7 snapshot comparison hardening missing or duplicated")
if "SnapshotConflict" not in ha:
    raise SystemExit("V1.7 snapshot conflict outcome missing")

print("PASS V1.7 terminal asset hardening verification")
