#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path


def replace_exact(path: Path, old: str, new: str, count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    actual = text.count(old)
    if actual != count:
        raise SystemExit(
            f"asset patch target mismatch for {path.name}: expected {count}, found {actual}: {old[:100]!r}"
        )
    path.write_text(text.replace(old, new, count), encoding="utf-8")


def patch(root: Path) -> None:
    replace_exact(
        root / "ha_core.rs",
        "fn snapshots_cannot_regress_or silently_change_equal_index_state()",
        "fn snapshots_cannot_regress_or_silently_change_equal_index_state()",
    )

    replace_exact(
        root / "plugin_host.rs",
        "use heptabao_plugin_contracts::{\n    PluginCapability, PluginContractError, PluginDescriptor, PluginDigest,\n};",
        "use heptabao_plugin_contracts::{PluginCapability, PluginContractError, PluginDescriptor};",
    )
    replace_exact(
        root / "plugin_host.rs",
        "use heptabao_plugin_contracts::{PluginId, PluginCapability};",
        "use heptabao_plugin_contracts::{PluginDigest, PluginId};",
    )

    replace_exact(
        root / "compat_runner.rs",
        "if !valid_header_name(name) || value.contains(['\\r', '\\n']) {",
        "if !valid_header_name(name) || value.chars().any(|character| matches!(character, '\\r' | '\\n')) {",
    )

    replace_exact(
        root / "client_tools.rs",
        "|| target.contains(['\\r', '\\n', '#', '\\\\'])",
        "|| target.chars().any(|character| matches!(character, '\\r' | '\\n' | '#' | '\\\\'))",
    )
    replace_exact(
        root / "client_tools.rs",
        "|| value.contains(['\\r', '\\n'])",
        "|| value.chars().any(|character| matches!(character, '\\r' | '\\n'))",
    )

    http = root / "http_api.rs"
    replace_exact(
        http,
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct HttpRequest",
        "#[derive(Clone, Eq, PartialEq)]\npub struct HttpRequest",
    )
    replace_exact(
        http,
        "#[derive(Clone, Debug, Eq, PartialEq)]\npub struct HttpResponse",
        "#[derive(Clone, Eq, PartialEq)]\npub struct HttpResponse",
    )
    marker = "impl HttpResponse {\n"
    debug_impls = '''impl fmt::Debug for HttpRequest {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("HttpRequest")
            .field("method", &self.method)
            .field("target_len", &self.target.len())
            .field("header_names", &self.headers.keys().collect::<Vec<_>>())
            .field("body_len", &self.body.len())
            .finish_non_exhaustive()
    }
}

impl fmt::Debug for HttpResponse {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("HttpResponse")
            .field("status", &self.status)
            .field("header_names", &self.headers.keys().collect::<Vec<_>>())
            .field("body_len", &self.body.len())
            .finish_non_exhaustive()
    }
}

'''
    replace_exact(http, marker, debug_impls + marker)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("asset_root", type=Path)
    args = parser.parse_args()
    root = args.asset_root.resolve()
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
            f"asset set mismatch: missing={sorted(required - present)} extra={sorted(present - required)}"
        )
    patch(root)
    print("PASS deterministic V1.7 asset hardening")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
