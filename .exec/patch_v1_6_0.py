#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
old = """    block=f'''{begin}\\n## V1.6.0 machine-verified module truth\\n\\nThe current workspace contains `{truth[\"module_count\"]}` source-bound crates. Run `python scripts/render_module_source_truth_v1_6_0.py --check`.\\n{end}'''"""
new = r"""    block=(
        f"{begin}\n"
        "## V1.6.0 machine-verified module truth\n\n"
        f"The current workspace contains `{truth['module_count']}` source-bound crates. "
        "Run `python scripts/render_module_source_truth_v1_6_0.py --check`.\n"
        f"{end}"
    )"""
count = text.count(old)
if count != 1:
    raise SystemExit(f"V1.6 generator patch target count mismatch: expected 1, found {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
print("patched V1.6 nested string delimiter")
