#!/usr/bin/env python3

from pathlib import Path
import sys

root = Path(sys.argv[1]).resolve()
path = root / "http_api.rs"
text = path.read_text(encoding="utf-8")
old = "let canonical_value = value.trim_matches([' ', '\\t']);"
new = "let canonical_value = value.trim_matches(|character| matches!(character, ' ' | '\\t'));"
if text.count(old) != 1:
    raise SystemExit("HTTP trim patch target mismatch")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("PASS V1.7 HTTP pattern compatibility patch")
