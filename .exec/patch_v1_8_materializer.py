#!/usr/bin/env python3
"""Repair the V1.8 materializer's nested renderer string delimiters.

The pinned V1.8 source embeds the generated module renderer inside a raw
triple-single-quoted Python string, but that embedded renderer also opens a
triple-single-quoted f-string.  The inner delimiter terminates the outer source
and makes the materializer unparsable.  This helper performs two exact-count
substitutions on the execution copy only, then compiles the repaired source.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

OPEN = "block=f'''<!-- BEGIN V1.8.0 MODULE TRUTH INDEX -->"
CLOSE = "<!-- END V1.8.0 MODULE TRUTH INDEX -->''';expected_index="
OPEN_REPLACEMENT = 'block=f"""<!-- BEGIN V1.8.0 MODULE TRUTH INDEX -->'
CLOSE_REPLACEMENT = '<!-- END V1.8.0 MODULE TRUTH INDEX -->""";expected_index='


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    args = parser.parse_args()

    raw = args.path.read_bytes()
    text = raw.decode("utf-8")
    if text.count(OPEN) != 1:
        raise SystemExit(f"V1.8 nested renderer opening count is {text.count(OPEN)}, expected 1")
    if text.count(CLOSE) != 1:
        raise SystemExit(f"V1.8 nested renderer closing count is {text.count(CLOSE)}, expected 1")
    if OPEN_REPLACEMENT in text or CLOSE_REPLACEMENT in text:
        raise SystemExit("V1.8 materializer unexpectedly already contains the delimiter repair")

    patched = text.replace(OPEN, OPEN_REPLACEMENT).replace(CLOSE, CLOSE_REPLACEMENT)
    compile(patched, str(args.path), "exec")
    args.path.write_text(patched, encoding="utf-8")
    print(
        "PASS repaired V1.8 nested renderer delimiters "
        f"source_sha256={digest(raw)} patched_sha256={digest(patched.encode('utf-8'))}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
