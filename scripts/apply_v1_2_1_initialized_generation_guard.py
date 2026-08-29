#!/usr/bin/env python3
# Apply the fail-closed initialized-generation guard to the H02 durable store.

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
PLAN = ROOT / "planning/HEPTABAO_H02_OS_DURABLE_CLOCK_BLOCKER_CLOSURE_V1.yaml"
REGISTER = ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1.yaml"
VALIDATOR = ROOT / "scripts/validate_h02_blocker_closure_v1.py"
DURABILITY = ROOT / "docs/architecture/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return text.replace(old, new, 1)


def patch_store() -> None:
    text = STORE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''const LOG_MAGIC: [u8; 8] = *b"HBRLOG01";
const STATE_BUNDLE_MAGIC: [u8; 8] = *b"HBRSB001";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);
''',
        '''const LOG_MAGIC: [u8; 8] = *b"HBRLOG01";
const STATE_BUNDLE_MAGIC: [u8; 8] = *b"HBRSB001";
const INITIALIZATION_MAGIC: [u8; 8] = *b"HBRINI01";
const INITIALIZATION_MARKER_FILE: &str = "initialized.bin";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);
''',
        "durable initialization constants",
    )
    text = replace_once(
        text,
        '''fn write_json<T>(path: &Path, magic: [u8; 8], value: &T) -> io::Result<()>
where
    T: Serialize,
{
    let payload = serde_json::to_vec(value).map_err(|error| invalid(error.to_string()))?;
    atomic_write(path, magic, &payload)
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
struct PersistentLogState {
''',
        '''fn write_json<T>(path: &Path, magic: [u8; 8], value: &T) -> io::Result<()>
where
    T: Serialize,
{
    let payload = serde_json::to_vec(value).map_err(|error| invalid(error.to_string()))?;
    atomic_write(path, magic, &payload)
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct PersistentInitializationMarker {
    format_version: u16,
    domain: String,
}

impl PersistentInitializationMarker {
    fn new(domain: &str) -> Self {
        Self {
            format_version: 1,
            domain: domain.to_owned(),
        }
    }

    fn validate(&self, expected_domain: &str) -> io::Result<()> {
        if self.format_version != 1 {
            return Err(invalid("unsupported initialization marker version"));
        }
        if self.domain != expected_domain {
            return Err(invalid(format!(
                "initialization marker domain mismatch: expected {expected_domain}, got {}",
                self.domain
            )));
        }
        Ok(())
    }
}

fn initialization_marker_path(root: &Path) -> PathBuf {
    root.join(INITIALIZATION_MARKER_FILE)
}

fn read_initialization_marker(root: &Path, expected_domain: &str) -> io::Result<bool> {
    let path = initialization_marker_path(root);
    recover_interrupted_replace(&path)?;
    if !path.is_file() {
        return Ok(false);
    }
    let marker: PersistentInitializationMarker = read_json(&path, INITIALIZATION_MAGIC)?;
    marker.validate(expected_domain)?;
    Ok(true)
}

fn persist_initialization_marker(root: &Path, domain: &str) -> io::Result<()> {
    write_json(
        &initialization_marker_path(root),
        INITIALIZATION_MAGIC,
        &PersistentInitializationMarker::new(domain),
    )
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
struct PersistentLogState {
''',
        "initialization marker contract",
    )
    text = replace_once(
        text,
        '''    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let state_path = root.join("raft-log.bin");
        let state = if state_path.is_file() {
            read_json(&state_path, LOG_MAGIC)?
        } else {
            PersistentLogState::default()
        };
        state.validate()?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }
''',
        '''    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let state_path = root.join("raft-log.bin");
        let marker_present = read_initialization_marker(root, "raft-log")?;
        recover_interrupted_replace(&state_path)?;

        let state = if state_path.is_file() {
            let state: PersistentLogState = read_json(&state_path, LOG_MAGIC)?;
            state.validate()?;
            if !marker_present {
                persist_initialization_marker(root, "raft-log")?;
            }
            state
        } else if marker_present {
            return Err(invalid(
                "initialized raft log store is missing its authoritative generation",
            ));
        } else {
            let initial = PersistentLogState::default();
            write_json(&state_path, LOG_MAGIC, &initial)?;
            persist_initialization_marker(root, "raft-log")?;
            initial
        };

        state.validate()?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }
''',
        "raft log open fail-closed contract",
    )
    text = replace_once(
        text,
        '''    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let bundle_path = root.join("state-bundle.bin");
        let bundle = if bundle_path.is_file() {
            read_json(&bundle_path, STATE_BUNDLE_MAGIC)?
        } else {
            let initial = PersistentStateBundle::default();
            write_json(&bundle_path, STATE_BUNDLE_MAGIC, &initial)?;
            initial
        };
        bundle.validate()?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }
''',
        '''    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let bundle_path = root.join("state-bundle.bin");
        let marker_present = read_initialization_marker(root, "state-machine")?;
        recover_interrupted_replace(&bundle_path)?;

        let bundle = if bundle_path.is_file() {
            let bundle: PersistentStateBundle = read_json(&bundle_path, STATE_BUNDLE_MAGIC)?;
            bundle.validate()?;
            if !marker_present {
                persist_initialization_marker(root, "state-machine")?;
            }
            bundle
        } else if marker_present {
            return Err(invalid(
                "initialized state machine is missing its authoritative generation",
            ));
        } else {
            let initial = PersistentStateBundle::default();
            write_json(&bundle_path, STATE_BUNDLE_MAGIC, &initial)?;
            persist_initialization_marker(root, "state-machine")?;
            initial
        };

        bundle.validate()?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }
''',
        "state bundle open fail-closed contract",
    )
    text = replace_once(
        text,
        '''    use super::{
        DurableLogStore, DurableStateMachine, LOG_MAGIC, PersistentLogState, PersistentStateBundle,
        RaftLogStorage, RaftSnapshotBuilder, STATE_BUNDLE_MAGIC, read_json, write_json,
    };
    use std::collections::BTreeMap;
    use std::fs;
''',
        '''    use super::{
        DurableLogStore, DurableStateMachine, INITIALIZATION_MARKER_FILE, LOG_MAGIC,
        PersistentLogState, PersistentStateBundle, RaftLogStorage, RaftSnapshotBuilder,
        STATE_BUNDLE_MAGIC, read_json, write_json,
    };
    use std::collections::BTreeMap;
    use std::fs;
    use std::io;
''',
        "test imports",
    )
    text = replace_once(
        text,
        '''    #[test]
    fn log_envelope_round_trip_remains_bounded() {
''',
        '''    #[test]
    fn fresh_stores_persist_authoritative_generation_and_marker() {
        let log_root = root("fresh-log-initialization");
        let log_store = DurableLogStore::open(&log_root).expect("initialize log store");
        assert!(log_store.state_path().is_file());
        assert!(log_root.join(INITIALIZATION_MARKER_FILE).is_file());

        let state_root = root("fresh-state-initialization");
        let state_machine =
            DurableStateMachine::open(&state_root).expect("initialize state machine");
        assert!(state_machine.state_path().is_file());
        assert!(state_root.join(INITIALIZATION_MARKER_FILE).is_file());

        let _ = fs::remove_dir_all(log_root);
        let _ = fs::remove_dir_all(state_root);
    }

    #[test]
    fn missing_initialized_log_generation_fails_closed() {
        let root = root("missing-log-generation");
        let store = DurableLogStore::open(&root).expect("initialize log store");
        fs::remove_file(store.state_path()).expect("remove authoritative log generation");

        let error = DurableLogStore::open(&root)
            .expect_err("initialized log store must reject missing authoritative generation");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn missing_initialized_state_generation_fails_closed() {
        let root = root("missing-state-generation");
        let state_machine =
            DurableStateMachine::open(&root).expect("initialize state machine");
        fs::remove_file(state_machine.state_path())
            .expect("remove authoritative state generation");

        let error = DurableStateMachine::open(&root)
            .expect_err("initialized state machine must reject missing authoritative generation");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn legacy_authoritative_generation_without_marker_is_adopted() {
        let root = root("legacy-generation-adoption");
        fs::create_dir_all(&root).expect("test root");
        let path = root.join("raft-log.bin");
        write_json(&path, LOG_MAGIC, &PersistentLogState::default()).expect("legacy state");
        assert!(!root.join(INITIALIZATION_MARKER_FILE).exists());

        let store = DurableLogStore::open(&root).expect("adopt legacy generation");
        assert!(store.state_path().is_file());
        assert!(root.join(INITIALIZATION_MARKER_FILE).is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn log_envelope_round_trip_remains_bounded() {
''',
        "initialized generation regression tests",
    )
    STORE.write_text(text, encoding="utf-8")


def patch_plan() -> None:
    text = PLAN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''      snapshot_metadata_and_membership_validated: true
    implemented_cases:
''',
        '''      snapshot_metadata_and_membership_validated: true
      initialized_store_marker_persisted: true
      missing_initialized_generation_fails_closed: true
    implemented_cases:
''',
        "durable plan persistence contract",
    )
    text = replace_once(
        text,
        '''      - state-machine corruption rejected on reopen
      - isolated writer cannot advance committed state
''',
        '''      - state-machine corruption rejected on reopen
      - initialized log generation deletion rejected on reopen
      - initialized state generation deletion rejected on reopen
      - legacy authoritative generation adopted only after validation and marker publication
      - isolated writer cannot advance committed state
''',
        "durable plan implemented cases",
    )
    text = replace_once(
        text,
        '''  - Missing external approvals and signed receipts remain real blockers and are never fabricated.
  - qualification=false, selection_effect=NONE and authority_effect=NONE are immutable.
''',
        '''  - Missing external approvals and signed receipts remain real blockers and are never fabricated.
  - Once an initialization marker exists, an absent authoritative generation is corruption and cannot be interpreted as a fresh store.
  - qualification=false, selection_effect=NONE and authority_effect=NONE are immutable.
''',
        "durable plan invariant",
    )
    PLAN.write_text(text, encoding="utf-8")


def patch_register() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  title: state machine and snapshot can cross generations
''',
        '''  title: state machine and snapshot can cross generations or silently reinitialize after generation loss
''',
        "blocker 007 title",
    )
    text = replace_once(
        text,
        '''  - state and snapshot are stored in one atomic versioned bundle or manifest
  - interrupted replacement recovery is explicit
  - corruption and reopen fail closed
  - exact-head durable matrix passes across required toolchains and seeds
''',
        '''  - state and snapshot are stored in one atomic versioned bundle or manifest
  - initialized store markers distinguish first bootstrap from authoritative generation loss
  - missing initialized log or state generations fail closed
  - legacy authoritative generations are adopted only after validation and marker publication
  - interrupted replacement recovery is explicit
  - corruption and reopen fail closed
  - exact-head durable matrix passes across required toolchains and seeds
''',
        "blocker 007 closure criteria",
    )
    REGISTER.write_text(text, encoding="utf-8")


def patch_validator() -> None:
    text = VALIDATOR.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''        ["RaftLogStorage", "RaftStateMachine", "RaftSnapshotBuilder", "sync_all", "IOFlushed"],
''',
        '''        [
            "RaftLogStorage",
            "RaftStateMachine",
            "RaftSnapshotBuilder",
            "sync_all",
            "IOFlushed",
            "INITIALIZATION_MARKER_FILE",
            "missing_initialized_log_generation_fails_closed",
            "missing_initialized_state_generation_fails_closed",
            "legacy_authoritative_generation_without_marker_is_adopted",
        ],
''',
        "integrated store validator markers",
    )
    VALIDATOR.write_text(text, encoding="utf-8")


def patch_durability_contract() -> None:
    text = DURABILITY.read_text(encoding="utf-8")
    heading = "## Initialized-store authoritative generation loss"
    if heading in text:
        raise RuntimeError("durability contract already contains initialized-generation rule")
    text = text.rstrip() + f'''\n\n{heading}\n\nA storage directory has two distinct states: never initialized, and initialized. The
implementation MUST persist a versioned initialization marker only after the first
authoritative generation has been durably published. On every later open:

1. interrupted replacement recovery is attempted before classification;
2. a valid marker plus a missing authoritative generation is corruption and fails closed;
3. a present authoritative generation without a marker may be adopted only after full
   envelope, schema and invariant validation, followed by durable marker publication;
4. neither a deleted log generation nor a deleted state/snapshot bundle may be interpreted
   as a fresh empty store;
5. tests MUST cover fresh initialization, legacy adoption, missing-generation rejection,
   corrupted marker rejection and interrupted replacement recovery.

This repository-level guard does not claim storage-controller cache persistence, kernel
power-cut safety or filesystem-specific crash consistency. Those remain separately
qualified external laboratory requirements.
'''
    DURABILITY.write_text(text, encoding="utf-8")


def main() -> int:
    patch_store()
    patch_plan()
    patch_register()
    patch_validator()
    patch_durability_contract()
    print("initialized-generation fail-closed guard applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
