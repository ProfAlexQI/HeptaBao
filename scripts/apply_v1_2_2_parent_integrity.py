#!/usr/bin/env python3
"""Apply the exact V1.2.2 durable parent-integrity closure."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
PLAN = ROOT / "planning/HEPTABAO_H02_OS_DURABLE_CLOCK_BLOCKER_CLOSURE_V1.yaml"
REGISTER = ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1.yaml"
VALIDATOR = ROOT / "scripts/validate_h02_blocker_closure_v1.py"
DURABILITY = ROOT / "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md"

EXPECTED_BLOBS = {
    STORE: "a4f90d29f981175637668f7fd44e758d6aa9c63c",
    PLAN: "625967d40f7e0f50f6374629136b63e645407d59",
    REGISTER: "e63d949a6a833d2d7fd107df8acc14c9cd93e6e0",
    VALIDATOR: "65264c4bfd86630bc0edbc7821f5f47235e67056",
    DURABILITY: "f083496f0e76ce8e7b552b21c102d575545cf434",
}


def blob(path: Path) -> str:
    return subprocess.run(
        ["git", "hash-object", str(path)],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def verify_base() -> None:
    expected_parent = "668cfa2f6d6cee8d3cde239ca02890973374809a"
    subprocess.run(
        ["git", "merge-base", "--is-ancestor", expected_parent, "HEAD"],
        cwd=ROOT,
        check=True,
    )
    for path, expected in EXPECTED_BLOBS.items():
        actual = blob(path)
        if actual != expected:
            raise RuntimeError(
                f"BASE_DRIFT {path.relative_to(ROOT)}: expected {expected}, got {actual}"
            )


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''    if !parent.is_dir() {
        return Ok(Vec::new());
    }
''',
        '''    require_real_directory(parent, "durable replacement parent directory")?;
''',
        "replacement parent validation",
    )
    text = replace_once(
        text,
        '''    fs::create_dir_all(parent)?;
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
''',
        '''    require_real_directory(parent, "durable write parent directory")?;
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
''',
        "active durable parent validation",
    )
    text = replace_once(
        text,
        '''    let encoded = encode_envelope(magic, payload)?;

    let result = (|| -> io::Result<()> {
''',
        '''    let encoded = encode_envelope(magic, payload)?;
    let current_exists = regular_file_status(path, "durable current generation")?;

    let result = (|| -> io::Result<()> {
''',
        "current generation preflight",
    )
    text = replace_once(
        text,
        '''        #[cfg(windows)]
        if path.exists() {
''',
        '''        #[cfg(windows)]
        if current_exists {
''',
        "Windows regular-file preflight",
    )
    text = replace_once(
        text,
        '''        #[cfg(not(windows))]
        fs::rename(&temporary, path)?;
''',
        '''        #[cfg(not(windows))]
        {
            let _ = current_exists;
            fs::rename(&temporary, path)?;
        }
''',
        "non-Windows current-generation preflight binding",
    )
    text = replace_once(
        text,
        '''        if !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker temporary artifacts",
            ));
        }
        recover_interrupted_replace(&state_path)?;
''',
        '''        if !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker temporary artifacts",
            ));
        }
        if !replacement_candidates(&state_path, ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved raft-log temporary artifacts",
            ));
        }
        recover_interrupted_replace(&state_path)?;
''',
        "legacy log temporary rejection",
    )
    text = replace_once(
        text,
        '''        if !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker temporary artifacts",
            ));
        }
        recover_interrupted_replace(&bundle_path)?;
''',
        '''        if !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker temporary artifacts",
            ));
        }
        if !replacement_candidates(&bundle_path, ".tmp")?.is_empty() {
            return Err(invalid(
                "legacy adoption refused unresolved state-bundle temporary artifacts",
            ));
        }
        recover_interrupted_replace(&bundle_path)?;
''',
        "legacy state temporary rejection",
    )

    anchor = '''    #[test]
    fn legacy_generation_requires_explicit_validated_adoption() {
'''
    tests = '''    #[tokio::test]
    async fn active_log_persist_does_not_recreate_deleted_store_root() {
        let root = root("active-log-deleted-root");
        let mut store = DurableLogStore::create(&root).expect("create log store");
        fs::remove_dir_all(&root).expect("remove active log root");

        let error = store
            .save_committed(None)
            .await
            .expect_err("active persistence must not recreate a deleted root");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.exists());
    }

    #[tokio::test]
    async fn active_state_persist_does_not_recreate_deleted_store_root() {
        let root = root("active-state-deleted-root");
        let mut state = DurableStateMachine::create(&root).expect("create state machine");
        fs::remove_dir_all(&root).expect("remove active state root");

        let error = state
            .build_snapshot()
            .await
            .expect_err("active persistence must not recreate a deleted root");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.exists());
    }

    #[test]
    fn legacy_log_adoption_rejects_unresolved_data_temporary_file() {
        let root = root("legacy-log-temporary");
        fs::create_dir_all(&root).expect("test root");
        write_json(
            &root.join("raft-log.bin"),
            LOG_MAGIC,
            &PersistentLogState::default(),
        )
        .expect("legacy log generation");
        fs::write(root.join(".raft-log.bin.1.1.tmp"), b"unresolved")
            .expect("legacy log temporary");

        let error = DurableLogStore::adopt_legacy(&root)
            .expect_err("legacy adoption must reject unresolved data temporary files");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.join(INITIALIZATION_MARKER_FILE).exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn legacy_state_adoption_rejects_unresolved_data_temporary_file() {
        let root = root("legacy-state-temporary");
        fs::create_dir_all(&root).expect("test root");
        write_json(
            &root.join("state-bundle.bin"),
            STATE_BUNDLE_MAGIC,
            &PersistentStateBundle::default(),
        )
        .expect("legacy state generation");
        fs::write(root.join(".state-bundle.bin.1.1.tmp"), b"unresolved")
            .expect("legacy state temporary");

        let error = DurableStateMachine::adopt_legacy(&root)
            .expect_err("legacy adoption must reject unresolved data temporary files");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.join(INITIALIZATION_MARKER_FILE).exists());
        let _ = fs::remove_dir_all(root);
    }

'''
    text = replace_once(text, anchor, tests + anchor, "parent-integrity tests")
    STORE.write_text(text, encoding="utf-8")


def patch_plan() -> None:
    text = PLAN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''      marker_domain_and_file_binding_validated: true
    implemented_cases:
''',
        '''      marker_domain_and_file_binding_validated: true
      active_persistence_requires_existing_real_parent: true
      legacy_data_temporary_artifacts_rejected: true
      current_generation_type_preflighted: true
    implemented_cases:
''',
        "plan persistence contract",
    )
    text = replace_once(
        text,
        '''      - legacy authoritative generation requires explicit validated adoption
      - valid current generation discards one stale previous only after validation
''',
        '''      - legacy authoritative generation requires explicit validated adoption
      - active persistence rejects deleted or replaced parent directories without recreating them
      - legacy adoption rejects unresolved raft-log and state-bundle temporary artifacts
      - existing current generations are regular-file checked before atomic replacement
      - valid current generation discards one stale previous only after validation
''',
        "plan implemented cases",
    )
    text = replace_once(
        text,
        '''  - Bootstrap creation, existing-store reopen and legacy adoption are distinct caller-selected operations.
''',
        '''  - Bootstrap creation, existing-store reopen and legacy adoption are distinct caller-selected operations.
  - Active persistence never recreates a missing durable parent directory and rejects non-directory replacement.
  - Legacy adoption is blocked by unresolved marker or authoritative-generation temporary artifacts.
''',
        "plan invariants",
    )
    PLAN.write_text(text, encoding="utf-8")


def patch_register() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  - legacy authoritative generations are adopted only after validation and marker
    publication
  - interrupted replacement recovery is explicit for generations and markers
''',
        '''  - legacy authoritative generations are adopted only after validation and marker
    publication
  - active persistence refuses missing, symlinked or non-directory parent paths without recreating them
  - legacy adoption rejects unresolved marker, raft-log and state-bundle temporary artifacts
  - current generation type is checked before every atomic replacement
  - interrupted replacement recovery is explicit for generations and markers
''',
        "blocker 007 criteria",
    )
    REGISTER.write_text(text, encoding="utf-8")


def patch_validator() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''            "symlinked_authoritative_generation_is_rejected",
            "symlink_metadata",
''',
        '''            "symlinked_authoritative_generation_is_rejected",
            "active_log_persist_does_not_recreate_deleted_store_root",
            "active_state_persist_does_not_recreate_deleted_store_root",
            "legacy_log_adoption_rejects_unresolved_data_temporary_file",
            "legacy_state_adoption_rejects_unresolved_data_temporary_file",
            "durable write parent directory",
            "durable replacement parent directory",
            "durable current generation",
            "symlink_metadata",
''',
        "integrated-store validation tokens",
    )
    VALIDATOR.write_text(text, encoding="utf-8")


def patch_durability() -> None:
    text = DURABILITY.read_text(encoding="utf-8").rstrip()
    heading = "## 9. Active-parent integrity and legacy temporary-state rejection"
    if heading in text:
        raise RuntimeError("durability section already present")
    text += f'''\n\n{heading}\n\nAn already opened durable domain MUST NOT recreate its storage root if that directory is\ndeleted, replaced by a symlink, or replaced by a non-directory object. Every durable write\npreflights the parent with `symlink_metadata`; failure is surfaced before a temporary file is\ncreated and before candidate state is published. This rule closes the gap between strict\n`reopen-existing` semantics and writes performed by a still-running process.\n\nBefore legacy adoption, both the initialization-marker path and the authoritative data path\nare scanned for unresolved `.tmp` artifacts. Any such artifact makes provenance ambiguous and\nblocks adoption. The operator must preserve and disposition the artifacts explicitly; the\nimplementation does not choose one generation, delete evidence, or manufacture a marker.\n\nBefore replacement, an existing current path must be a regular file. Symlinks, directories,\ndevices, and other non-regular objects fail closed on all platforms. Tests cover active log\nand state-root deletion plus unresolved log/state temporary files. These controls remain\nrepository-level logical guarantees and do not replace kernel/VM power-cut evidence.\n'''
    DURABILITY.write_text(text, encoding="utf-8")


def main() -> int:
    verify_base()
    patch_store()
    patch_plan()
    patch_register()
    patch_validator()
    patch_durability()
    subprocess.run(["git", "diff", "--check"], cwd=ROOT, check=True)
    print("V1.2.2 durable parent-integrity closure applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
