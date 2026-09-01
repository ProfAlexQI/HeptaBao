#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, expected: int = 1) -> None:
    file = Path(path)
    value = file.read_text(encoding="utf-8")
    actual = value.count(old)
    if actual != expected:
        raise SystemExit(f"{path}: expected {expected} matches, found {actual}: {old[:120]!r}")
    file.write_text(value.replace(old, new, expected), encoding="utf-8")


path = "crates/heptabao-recovery-core/src/lib.rs"
replace(
    path,
    "    use heptabao_storage_api::{CommitReceipt, GenerationSnapshot, OpaqueState, StoreOpenMode};\n",
    "    use heptabao_storage_api::{\n"
    "        CommitIntent, CommitReceipt, CommitRecovery, GenerationSnapshot, OpaqueState,\n"
    "        StoreOpenMode,\n"
    "    };\n",
)
replace(
    path,
    "        fn commit(\n"
    "            &mut self,\n"
    "            _expected_current: Option<Generation>,\n"
    "            _candidate: OpaqueState,\n"
    "        ) -> Result<CommitReceipt, Self::Error> {\n"
    "            Err(TestError::Contract)\n"
    "        }\n",
    "        fn prepare_commit(\n"
    "            &self,\n"
    "            _expected_current: Option<Generation>,\n"
    "            _candidate: &OpaqueState,\n"
    "        ) -> Result<CommitIntent, Self::Error> {\n"
    "            Err(TestError::Contract)\n"
    "        }\n\n"
    "        fn recover_commit(\n"
    "            &mut self,\n"
    "            _intent: CommitIntent,\n"
    "        ) -> Result<CommitRecovery, Self::Error> {\n"
    "            Err(TestError::Contract)\n"
    "        }\n\n"
    "        fn commit(\n"
    "            &mut self,\n"
    "            _expected_current: Option<Generation>,\n"
    "            _candidate: OpaqueState,\n"
    "        ) -> Result<CommitReceipt, Self::Error> {\n"
    "            Err(TestError::Contract)\n"
    "        }\n",
)
print("V1.4.6 storage intent compile fix applied")
