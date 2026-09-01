#!/usr/bin/env python3
from pathlib import Path


def replace(path: str, old: str, new: str, expected: int = 1) -> None:
    file = Path(path)
    value = file.read_text(encoding="utf-8")
    actual = value.count(old)
    if actual != expected:
        raise SystemExit(f"{path}: expected {expected} matches, found {actual}: {old[:120]!r}")
    file.write_text(value.replace(old, new, expected), encoding="utf-8")


path = "crates/heptabao-single-node-store/src/lib.rs"
replace(
    path,
    """                if intent.previous().is_none() && !marker_exists {
                    if self.publish_marker().is_err() {
                        return Err(FileStoreError::CommitOutcomeUnknown);
                    }
                }
""",
    """                if intent.previous().is_none()
                    && !marker_exists
                    && self.publish_marker().is_err()
                {
                    return Err(FileStoreError::CommitOutcomeUnknown);
                }
""",
)
replace(
    path,
    """                        assert_eq!(store.recover_commit(intent), Ok(CommitRecovery::NotCommitted));
""",
    """                        assert!(matches!(
                            store.recover_commit(intent),
                            Ok(CommitRecovery::NotCommitted)
                        ));
""",
)
replace(
    path,
    """                        assert_eq!(
                            store.recover_commit(intent),
                            Ok(CommitRecovery::Committed(intent.receipt()))
                        );
""",
    """                        let recovered = store.recover_commit(intent);
                        assert!(matches!(
                            recovered,
                            Ok(CommitRecovery::Committed(receipt))
                                if receipt == intent.receipt()
                        ));
""",
)
replace(
    path,
    """                            assert_eq!(
                                store.recover_commit(intent),
                                Ok(CommitRecovery::Committed(intent.receipt()))
                            );
""",
    """                            let recovered = store.recover_commit(intent);
                            assert!(matches!(
                                recovered,
                                Ok(CommitRecovery::Committed(receipt))
                                    if receipt == intent.receipt()
                            ));
""",
)
print("V1.4.6 storage intent strict-gate fix applied")
