#!/usr/bin/env python3
from pathlib import Path

path = Path("crates/heptabao-single-node-store/src/lib.rs")
value = path.read_text(encoding="utf-8")
old = "                        let encoded = encode_bundle(\n"
new = "                        let encoded = encode_bundle::<TestIntegrityError>(\n"
if value.count(old) != 1:
    raise SystemExit(f"expected one direct test encode_bundle call, found {value.count(old)}")
path.write_text(value.replace(old, new, 1), encoding="utf-8")
print("V1.4.6 storage intent generic test fix applied")
