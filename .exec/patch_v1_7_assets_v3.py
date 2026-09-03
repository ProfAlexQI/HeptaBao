#!/usr/bin/env python3

from pathlib import Path
import re
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

generator = root.parent / "materialize_v1_7_0.py"
if not generator.is_file():
    raise SystemExit(f"V1.7 materializer missing beside asset root: {generator}")
source = generator.read_text(encoding="utf-8")
dynamic_pr = (
    'int(__import__("json").loads('
    '(__import__("pathlib").Path(__import__("os").environ["RUNNER_TEMP"]) '
    '/ "v1.6.0-admission.json").read_text(encoding="utf-8"))'
    '["pull_request"])'
)
if dynamic_pr not in source:
    source, count = re.subn(
        r'("pull_request"\s*:\s*)65\b',
        lambda match: match.group(1) + dynamic_pr,
        source,
    )
    if count != 1:
        raise SystemExit(
            f"V1.7 predecessor receipt patch target mismatch: expected 1, found {count}"
        )
    generator.write_text(source, encoding="utf-8")
elif source.count(dynamic_pr) != 1:
    raise SystemExit("V1.7 dynamic predecessor receipt binding is duplicated")

print("PASS V1.7 terminal asset and predecessor receipt hardening")
