#!/usr/bin/env python3
from pathlib import Path

path = Path("crates/heptabao-durable-core/src/lib.rs")
value = path.read_text(encoding="utf-8")
old = """                    assert_eq!(
                        engine.commit_prepared(prepared).map(|value| value.committed),
                        Ok(Generation::INITIAL)
                    );
"""
new = """                    let committed = engine.commit_prepared(prepared);
                    assert!(committed.is_ok());
                    if let Ok(receipt) = committed {
                        assert_eq!(receipt.committed, Generation::INITIAL);
                    }
"""
if value.count(old) != 1:
    raise SystemExit(f"expected one durable-core test assertion, found {value.count(old)}")
path.write_text(value.replace(old, new, 1), encoding="utf-8")
print("V1.4.6 storage intent test fix applied")
