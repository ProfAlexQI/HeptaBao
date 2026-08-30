# Protocol sensitive-rejection hygiene pending contract

Status: `LOCAL_PATCH_VALIDATED / REMOTE_BLOB_AND_EXACT_HEAD_REQUIRED`

The exact patch is staged on `exec/v1-3-protocol-hygiene-v1` and has passed the focused source contract locally. It must not be represented as merged or remotely executed until the final `crates/heptabao-protocol/src/lib.rs` blob is reachable from `codex/plan-v1.3-gap-closure-v2` and exact-head gates execute.

Required final markers:

- `SensitiveQueryMap(BTreeMap<String, String>)` owns already allocated query pairs and zeroizes them on parse rejection;
- duplicate query keys are detected before replacement allocation;
- duplicate headers are detected before replacing and releasing the previously accepted value;
- `tests/plan/test_sensitive_parse_rejection_hygiene.py` returns to the automatically discovered plan test suite;
- root Rust fmt/test/Clippy and the aggregate exact-head gate pass.

This object grants no qualification, compatibility, selection or authority.
