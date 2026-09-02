#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
replacements = [
    ('let remote:"192.0.2.1:8200".parse();', 'let remote = "192.0.2.1:8200".parse();'),
    ('let local:"127.0.0.1:8200".parse();', 'let local = "127.0.0.1:8200".parse();'),
    ('["CredentialExpired","TlsRequired","filter_headers"]', '["AgentError::Expired","TlsRequired","filter_headers"]'),
    ('format!("service-request-{:08}",body.len()+target.len())', 'format!("service-request-{:08}",REQUEST_COUNTER.fetch_add(1,Ordering::Relaxed))'),
    ('#[cfg(test)]mod tests{use std::collections::BTreeSet;use super::*;', '#[cfg(test)]mod tests{use std::collections::BTreeSet;use std::sync::atomic::{AtomicU64,Ordering};use super::*;'),
    ('fn handler(fail_outcome:bool)->Option<RuntimeHttpHandler<Seal,MemoryAuditSink,FixedClock>>{', 'static REQUEST_COUNTER:AtomicU64=AtomicU64::new(1);fn handler(fail_outcome:bool)->Option<RuntimeHttpHandler<Seal,MemoryAuditSink,FixedClock>>{'),
]
for old, new in replacements:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"patch target count mismatch for {old!r}: {count}")
    text = text.replace(old, new, 1)
path.write_text(text, encoding="utf-8")
print(f"patched {len(replacements)} V1.8.0 materializer targets")
