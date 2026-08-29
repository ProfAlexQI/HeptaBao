#!/usr/bin/env python3
'''Apply the V1.2.1 explicit durable-store lifecycle and generation-loss closure.'''

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORE = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
CLUSTER = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/cluster.rs"
DURABLE_MAIN = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs"
PLAN = ROOT / "planning/HEPTABAO_H02_OS_DURABLE_CLOCK_BLOCKER_CLOSURE_V1.yaml"
REGISTER = ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1.yaml"
VALIDATOR = ROOT / "scripts/validate_h02_blocker_closure_v1.py"
DURABILITY = ROOT / "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md"


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
const LOG_DOMAIN: &str = "raft-log";
const STATE_MACHINE_DOMAIN: &str = "state-machine";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);
''',
        "durable initialization constants",
    )
    text = replace_once(
        text,
        '''fn recover_interrupted_replace(path: &Path) -> io::Result<()> {
    if path.exists() {
        return Ok(());
    }
    let parent = path
        .parent()
        .ok_or_else(|| invalid(format!("{} has no parent directory", path.display())))?;
    if !parent.is_dir() {
        return Ok(());
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| invalid("durable file name is not valid UTF-8"))?;
    let prefix = format!(".{file_name}.");
    let mut previous = fs::read_dir(parent)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|candidate| {
            candidate
                .file_name()
                .and_then(|value| value.to_str())
                .is_some_and(|name| name.starts_with(&prefix) && name.ends_with(".previous"))
        })
        .collect::<Vec<_>>();
    previous.sort();
    match previous.as_slice() {
        [] => Ok(()),
        [candidate] => {
            fs::rename(candidate, path)?;
            sync_parent(path)
        }
        _ => Err(invalid(format!(
            "multiple interrupted replacement candidates for {}",
            path.display()
        ))),
    }
}
''',
        '''fn replacement_candidates(path: &Path, suffix: &str) -> io::Result<Vec<PathBuf>> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid(format!("{} has no parent directory", path.display())))?;
    if !parent.is_dir() {
        return Ok(Vec::new());
    }
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| invalid("durable file name is not valid UTF-8"))?;
    let prefix = format!(".{file_name}.");
    let mut candidates = Vec::new();
    for entry in fs::read_dir(parent)? {
        let entry = entry?;
        let candidate = entry.path();
        let matches = candidate
            .file_name()
            .and_then(|value| value.to_str())
            .is_some_and(|name| name.starts_with(&prefix) && name.ends_with(suffix));
        if matches {
            candidates.push(candidate);
        }
    }
    candidates.sort();
    Ok(candidates)
}

fn recover_interrupted_replace(path: &Path) -> io::Result<()> {
    if path.exists() {
        return Ok(());
    }
    let previous = replacement_candidates(path, ".previous")?;
    match previous.as_slice() {
        [] => Ok(()),
        [candidate] => {
            fs::rename(candidate, path)?;
            sync_parent(path)
        }
        _ => Err(invalid(format!(
            "multiple interrupted replacement candidates for {}",
            path.display()
        ))),
    }
}

fn discard_stale_previous_after_validation(path: &Path) -> io::Result<()> {
    if !path.is_file() {
        return Err(invalid(format!(
            "cannot discard replacement history without validated current file: {}",
            path.display()
        )));
    }
    let previous = replacement_candidates(path, ".previous")?;
    match previous.as_slice() {
        [] => Ok(()),
        [candidate] => {
            fs::remove_file(candidate)?;
            sync_parent(path)
        }
        _ => Err(invalid(format!(
            "multiple stale replacement candidates for {}",
            path.display()
        ))),
    }
}

fn ensure_create_location_is_fresh(root: &Path, data_path: &Path) -> io::Result<()> {
    let entries = fs::read_dir(root)?
        .map(|entry| entry.map(|value| value.path()))
        .collect::<io::Result<Vec<_>>>()?;
    if !entries.is_empty() {
        return Err(invalid(format!(
            "create-new refused nonempty store directory for {}: {}",
            data_path.display(),
            entries
                .iter()
                .map(|path| path.display().to_string())
                .collect::<Vec<_>>()
                .join(", ")
        )));
    }
    Ok(())
}
''',
        "replacement recovery protocol",
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
    authoritative_file: String,
}

impl PersistentInitializationMarker {
    fn new(domain: &str, authoritative_file: &str) -> Self {
        Self {
            format_version: 1,
            domain: domain.to_owned(),
            authoritative_file: authoritative_file.to_owned(),
        }
    }

    fn validate(&self, expected_domain: &str, expected_file: &str) -> io::Result<()> {
        if self.format_version != 1 {
            return Err(invalid("unsupported initialization marker version"));
        }
        if self.domain != expected_domain || self.authoritative_file != expected_file {
            return Err(invalid(format!(
                "initialization marker binding mismatch: expected {expected_domain}/{expected_file}, got {}/{}",
                self.domain, self.authoritative_file
            )));
        }
        Ok(())
    }
}

fn initialization_marker_path(root: &Path) -> PathBuf {
    root.join(INITIALIZATION_MARKER_FILE)
}

fn read_initialization_marker(
    root: &Path,
    expected_domain: &str,
    expected_file: &str,
) -> io::Result<Option<PersistentInitializationMarker>> {
    let path = initialization_marker_path(root);
    recover_interrupted_replace(&path)?;
    if !path.is_file() {
        return Ok(None);
    }
    let marker: PersistentInitializationMarker = read_json(&path, INITIALIZATION_MAGIC)?;
    marker.validate(expected_domain, expected_file)?;
    discard_stale_previous_after_validation(&path)?;
    Ok(Some(marker))
}

fn persist_initialization_marker(
    root: &Path,
    domain: &str,
    authoritative_file: &str,
) -> io::Result<()> {
    write_json(
        &initialization_marker_path(root),
        INITIALIZATION_MAGIC,
        &PersistentInitializationMarker::new(domain, authoritative_file),
    )
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
struct PersistentLogState {
''',
        "initialization marker contract",
    )
    text = replace_once(
        text,
        '''impl DurableLogStore {
    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
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

    fn persist(&self, state: &PersistentLogState) -> io::Result<()> {
''',
        '''impl DurableLogStore {
    pub fn create(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let state_path = root.join("raft-log.bin");
        ensure_create_location_is_fresh(root, &state_path)?;
        let state = PersistentLogState::default();
        write_json(&state_path, LOG_MAGIC, &state)?;
        persist_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }

    pub fn open_existing(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        if !root.is_dir() {
            return Err(invalid("raft log store directory does not exist"));
        }
        let state_path = root.join("raft-log.bin");
        let marker = read_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        if marker.is_none() {
            return Err(invalid(
                "raft log store is not initialized; explicit legacy adoption is required",
            ));
        }
        recover_interrupted_replace(&state_path)?;
        if !state_path.is_file() {
            return Err(invalid(
                "initialized raft log store is missing its authoritative generation",
            ));
        }
        let state: PersistentLogState = read_json(&state_path, LOG_MAGIC)?;
        state.validate()?;
        discard_stale_previous_after_validation(&state_path)?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        if !root.is_dir() {
            return Err(invalid("legacy raft log store directory does not exist"));
        }
        let state_path = root.join("raft-log.bin");
        if read_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?.is_some() {
            return Err(invalid(
                "raft log store already has an initialization marker; use open_existing",
            ));
        }
        if !replacement_candidates(&initialization_marker_path(root), ".previous")?.is_empty()
            || !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty()
        {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker artifacts",
            ));
        }
        recover_interrupted_replace(&state_path)?;
        if !state_path.is_file() {
            return Err(invalid(
                "legacy raft log store has no authoritative generation",
            ));
        }
        let state: PersistentLogState = read_json(&state_path, LOG_MAGIC)?;
        state.validate()?;
        discard_stale_previous_after_validation(&state_path)?;
        persist_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }

    fn persist(&self, state: &PersistentLogState) -> io::Result<()> {
''',
        "raft log explicit lifecycle",
    )
    text = replace_once(
        text,
        '''impl DurableStateMachine {
    pub fn open(root: impl AsRef<Path>) -> io::Result<Self> {
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

    fn persist_bundle(&self, bundle: &PersistentStateBundle) -> io::Result<()> {
''',
        '''impl DurableStateMachine {
    pub fn create(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let bundle_path = root.join("state-bundle.bin");
        ensure_create_location_is_fresh(root, &bundle_path)?;
        let bundle = PersistentStateBundle::default();
        write_json(&bundle_path, STATE_BUNDLE_MAGIC, &bundle)?;
        persist_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    pub fn open_existing(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        if !root.is_dir() {
            return Err(invalid("state-machine directory does not exist"));
        }
        let bundle_path = root.join("state-bundle.bin");
        let marker =
            read_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        if marker.is_none() {
            return Err(invalid(
                "state machine is not initialized; explicit legacy adoption is required",
            ));
        }
        recover_interrupted_replace(&bundle_path)?;
        if !bundle_path.is_file() {
            return Err(invalid(
                "initialized state machine is missing its authoritative generation",
            ));
        }
        let bundle: PersistentStateBundle = read_json(&bundle_path, STATE_BUNDLE_MAGIC)?;
        bundle.validate()?;
        discard_stale_previous_after_validation(&bundle_path)?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
        let root = root.as_ref();
        if !root.is_dir() {
            return Err(invalid("legacy state-machine directory does not exist"));
        }
        let bundle_path = root.join("state-bundle.bin");
        if read_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?.is_some() {
            return Err(invalid(
                "state machine already has an initialization marker; use open_existing",
            ));
        }
        if !replacement_candidates(&initialization_marker_path(root), ".previous")?.is_empty()
            || !replacement_candidates(&initialization_marker_path(root), ".tmp")?.is_empty()
        {
            return Err(invalid(
                "legacy adoption refused unresolved initialization-marker artifacts",
            ));
        }
        recover_interrupted_replace(&bundle_path)?;
        if !bundle_path.is_file() {
            return Err(invalid(
                "legacy state machine has no authoritative generation",
            ));
        }
        let bundle: PersistentStateBundle = read_json(&bundle_path, STATE_BUNDLE_MAGIC)?;
        bundle.validate()?;
        discard_stale_previous_after_validation(&bundle_path)?;
        persist_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    fn persist_bundle(&self, bundle: &PersistentStateBundle) -> io::Result<()> {
''',
        "state machine explicit lifecycle",
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
        STATE_BUNDLE_MAGIC, flip_first_payload_byte, read_json, write_json,
    };
    use std::collections::BTreeMap;
    use std::fs;
    use std::io;
''',
        "durable tests imports",
    )
    text = replace_once(
        text,
        '''    #[test]
    fn log_envelope_round_trip_remains_bounded() {
''',
        '''    #[test]
    fn fresh_create_and_existing_reopen_are_explicit() {
        let log_root = root("fresh-log-lifecycle");
        let log = DurableLogStore::create(&log_root).expect("create log store");
        assert!(log.state_path().is_file());
        assert!(log_root.join(INITIALIZATION_MARKER_FILE).is_file());
        DurableLogStore::open_existing(&log_root).expect("reopen log store");

        let state_root = root("fresh-state-lifecycle");
        let state = DurableStateMachine::create(&state_root).expect("create state machine");
        assert!(state.state_path().is_file());
        assert!(state_root.join(INITIALIZATION_MARKER_FILE).is_file());
        DurableStateMachine::open_existing(&state_root).expect("reopen state machine");

        let _ = fs::remove_dir_all(log_root);
        let _ = fs::remove_dir_all(state_root);
    }

    #[test]
    fn missing_initialized_log_generation_fails_closed() {
        let root = root("missing-log-generation");
        let store = DurableLogStore::create(&root).expect("create log store");
        fs::remove_file(store.state_path()).expect("remove authoritative log generation");
        let error = DurableLogStore::open_existing(&root)
            .expect_err("initialized log store must reject missing generation");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn missing_initialized_state_generation_fails_closed() {
        let root = root("missing-state-generation");
        let state = DurableStateMachine::create(&root).expect("create state machine");
        fs::remove_file(state.state_path()).expect("remove authoritative state generation");
        let error = DurableStateMachine::open_existing(&root)
            .expect_err("initialized state machine must reject missing generation");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn deleted_store_directory_is_not_silently_recreated_on_reopen() {
        let root = root("deleted-store-directory");
        DurableLogStore::create(&root).expect("create log store");
        fs::remove_dir_all(&root).expect("remove store directory");
        let error = DurableLogStore::open_existing(&root)
            .expect_err("reopen must not recreate a deleted store");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
    }

    #[test]
    fn legacy_generation_requires_explicit_validated_adoption() {
        let root = root("legacy-generation-adoption");
        fs::create_dir_all(&root).expect("test root");
        let path = root.join("raft-log.bin");
        write_json(&path, LOG_MAGIC, &PersistentLogState::default()).expect("legacy state");
        assert!(!root.join(INITIALIZATION_MARKER_FILE).exists());
        assert!(DurableLogStore::open_existing(&root).is_err());

        let store = DurableLogStore::adopt_legacy(&root).expect("adopt legacy generation");
        assert!(store.state_path().is_file());
        assert!(root.join(INITIALIZATION_MARKER_FILE).is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn valid_current_generation_discards_one_stale_previous() {
        let root = root("stale-previous-cleanup");
        let store = DurableLogStore::create(&root).expect("create log store");
        let previous = root.join(".raft-log.bin.1.1.previous");
        fs::copy(store.state_path(), &previous).expect("copy stale previous");
        DurableLogStore::open_existing(&root).expect("validate current generation");
        assert!(!previous.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn corrupt_current_generation_never_falls_back_to_previous() {
        let root = root("corrupt-current-no-rollback");
        let store = DurableLogStore::create(&root).expect("create log store");
        let previous = root.join(".raft-log.bin.1.1.previous");
        fs::copy(store.state_path(), &previous).expect("copy previous generation");
        flip_first_payload_byte(store.state_path()).expect("corrupt current generation");

        assert!(DurableLogStore::open_existing(&root).is_err());
        assert!(store.state_path().is_file());
        assert!(previous.is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn multiple_previous_generations_are_ambiguous_and_fail_closed() {
        let root = root("ambiguous-previous-generations");
        let store = DurableLogStore::create(&root).expect("create log store");
        let first = root.join(".raft-log.bin.1.1.previous");
        let second = root.join(".raft-log.bin.1.2.previous");
        fs::copy(store.state_path(), &first).expect("copy first previous");
        fs::copy(store.state_path(), &second).expect("copy second previous");
        fs::remove_file(store.state_path()).expect("remove current generation");

        assert!(DurableLogStore::open_existing(&root).is_err());
        assert!(first.is_file());
        assert!(second.is_file());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn corrupt_initialization_marker_fails_closed() {
        let root = root("corrupt-initialization-marker");
        DurableStateMachine::create(&root).expect("create state machine");
        flip_first_payload_byte(&root.join(INITIALIZATION_MARKER_FILE))
            .expect("corrupt initialization marker");
        assert!(DurableStateMachine::open_existing(&root).is_err());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn log_envelope_round_trip_remains_bounded() {
''',
        "initialized generation regression tests",
    )
    STORE.write_text(text, encoding="utf-8")


def patch_cluster() -> None:
    text = CLUSTER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''pub type AnyResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

pub struct DurableNode {
''',
        '''pub type AnyResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

#[derive(Clone, Copy, Debug)]
enum StoreLifecycle {
    CreateNew,
    ReopenExisting,
}

pub struct DurableNode {
''',
        "cluster lifecycle enum",
    )
    text = replace_once(
        text,
        '''    async fn open_stores(root: PathBuf) -> AnyResult<(DurableLogStore, DurableStateMachine)> {
        let stores = spawn_blocking(move || {
            let log_store = DurableLogStore::open(root.join("log"))?;
            let state_machine = DurableStateMachine::open(root.join("state-machine"))?;
            Ok::<_, std::io::Error>((log_store, state_machine))
        })
        .await??;
        Ok(stores)
    }

    pub async fn start_node(&mut self, id: u64) -> AnyResult<()> {
        if self.nodes.contains_key(&id) {
            return Err(format!("node {id} is already started").into());
        }
        let (log_store, state_machine) = Self::open_stores(self.node_root(id)).await?;
''',
        '''    async fn open_stores(
        root: PathBuf,
        lifecycle: StoreLifecycle,
    ) -> AnyResult<(DurableLogStore, DurableStateMachine)> {
        let stores = spawn_blocking(move || {
            let (log_store, state_machine) = match lifecycle {
                StoreLifecycle::CreateNew => (
                    DurableLogStore::create(root.join("log"))?,
                    DurableStateMachine::create(root.join("state-machine"))?,
                ),
                StoreLifecycle::ReopenExisting => (
                    DurableLogStore::open_existing(root.join("log"))?,
                    DurableStateMachine::open_existing(root.join("state-machine"))?,
                ),
            };
            Ok::<_, std::io::Error>((log_store, state_machine))
        })
        .await??;
        Ok(stores)
    }

    async fn start_node(&mut self, id: u64, lifecycle: StoreLifecycle) -> AnyResult<()> {
        if self.nodes.contains_key(&id) {
            return Err(format!("node {id} is already started").into());
        }
        let (log_store, state_machine) =
            Self::open_stores(self.node_root(id), lifecycle).await?;
''',
        "cluster store lifecycle routing",
    )
    text = replace_once(
        text,
        "        self.start_node(1).await?;\n",
        "        self.start_node(1, StoreLifecycle::CreateNew).await?;\n",
        "bootstrap first node lifecycle",
    )
    old = "            self.start_node(id).await?;\n"
    if text.count(old) != 2:
        raise RuntimeError(
            f"cluster start-node calls: expected two loop matches, found {text.count(old)}"
        )
    text = text.replace(
        old,
        "            self.start_node(id, StoreLifecycle::CreateNew).await?;\n",
        1,
    )
    text = text.replace(
        old,
        '''            self.start_node(id, StoreLifecycle::ReopenExisting)
                .await?;
''',
        1,
    )
    CLUSTER.write_text(text, encoding="utf-8")


def patch_durable_main() -> None:
    text = DURABLE_MAIN.read_text(encoding="utf-8")
    replacements = [
        (
            "DurableStateMachine::open(snapshot_copy)",
            "DurableStateMachine::open_existing(snapshot_copy)",
        ),
        (
            "DurableLogStore::open(corrupt_log_root)",
            "DurableLogStore::open_existing(corrupt_log_root)",
        ),
        (
            "DurableStateMachine::open(corrupt_state_root)",
            "DurableStateMachine::open_existing(corrupt_state_root)",
        ),
    ]
    for old, new in replacements:
        text = replace_once(text, old, new, f"durable main {old}")
    DURABLE_MAIN.write_text(text, encoding="utf-8")


def patch_plan() -> None:
    text = PLAN.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''      snapshot_metadata_and_membership_validated: true
    implemented_cases:
''',
        '''      snapshot_metadata_and_membership_validated: true
      explicit_create_reopen_lifecycle: true
      initialized_store_marker_persisted: true
      missing_initialized_generation_fails_closed: true
      validated_current_discards_single_stale_previous: true
      corrupt_current_never_falls_back_to_previous: true
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
      - bootstrap uses explicit create-new while restart uses explicit reopen-existing
      - initialized log generation deletion rejected on reopen
      - initialized state generation deletion rejected on reopen
      - deleted initialized directory is not silently recreated by the reopen path
      - legacy authoritative generation requires explicit validated adoption
      - valid current generation discards one stale previous generation after validation
      - corrupt current generation never falls back to an older previous generation
      - multiple previous generations fail closed as ambiguous
      - isolated writer cannot advance committed state
''',
        "durable plan implemented cases",
    )
    text = replace_once(
        text,
        '''      filesystem_crash_consistency_lab: false
''',
        '''      filesystem_crash_consistency_lab: false
      silent_fresh_reinitialization_on_reopen: false
''',
        "durable scope limit",
    )
    text = replace_once(
        text,
        '''  - Missing external approvals and signed receipts remain real blockers and are never fabricated.
  - qualification=false, selection_effect=NONE and authority_effect=NONE are immutable.
''',
        '''  - Missing external approvals and signed receipts remain real blockers and are never fabricated.
  - Bootstrap creation, existing-store reopen and legacy adoption are distinct caller-selected operations.
  - A missing marker or authoritative generation on the reopen path is corruption, never permission to initialize empty state.
  - A validated current generation may retire one stale previous file; corrupt current state must never roll back silently.
  - qualification=false, selection_effect=NONE and authority_effect=NONE are immutable.
''',
        "durable plan lifecycle invariants",
    )
    PLAN.write_text(text, encoding="utf-8")


def patch_register() -> None:
    text = REGISTER.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''  title: state machine and snapshot can cross generations
''',
        '''  title: durable generations can cross, disappear, or roll back through ambiguous reopen semantics
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
  - bootstrap create-new and recovery reopen-existing are distinct operations
  - versioned domain-bound initialization markers are persisted after first authoritative publication
  - missing initialized log or state generations fail closed
  - legacy generations require explicit validation and adoption
  - interrupted replacement recovery is explicit
  - a valid current generation retires stale previous state only after validation
  - corrupt current state never silently falls back to an older previous generation
  - multiple previous generations fail closed as ambiguous
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
        '''DURABLE_MAIN = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs"
DURABLE_STORE = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
''',
        '''DURABLE_MAIN = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab.rs"
DURABLE_STORE = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs"
DURABLE_CLUSTER = ROOT / "probes/h02/openraft-tokio/src/bin/durable_store_lab/cluster.rs"
''',
        "validator cluster path",
    )
    text = replace_once(
        text,
        '''    DURABLE_MAIN,
    DURABLE_STORE,
]
''',
        '''    DURABLE_MAIN,
    DURABLE_STORE,
    DURABLE_CLUSTER,
]
''',
        "validator required cluster",
    )
    text = replace_once(
        text,
        '''    require_tokens(
        DURABLE_STORE,
        ["RaftLogStorage", "RaftStateMachine", "RaftSnapshotBuilder", "sync_all", "IOFlushed"],
    )
    require_tokens(
        DURABLE_MAIN,
''',
        '''    require_tokens(
        DURABLE_STORE,
        [
            "RaftLogStorage",
            "RaftStateMachine",
            "RaftSnapshotBuilder",
            "sync_all",
            "IOFlushed",
            "INITIALIZATION_MARKER_FILE",
            "pub fn create(",
            "pub fn open_existing(",
            "pub fn adopt_legacy(",
            "discard_stale_previous_after_validation",
            "missing_initialized_log_generation_fails_closed",
            "missing_initialized_state_generation_fails_closed",
            "deleted_store_directory_is_not_silently_recreated_on_reopen",
            "legacy_generation_requires_explicit_validated_adoption",
            "corrupt_current_generation_never_falls_back_to_previous",
            "multiple_previous_generations_are_ambiguous_and_fail_closed",
        ],
    )
    require_tokens(
        DURABLE_CLUSTER,
        [
            "StoreLifecycle::CreateNew",
            "StoreLifecycle::ReopenExisting",
            "DurableLogStore::create",
            "DurableStateMachine::create",
            "DurableLogStore::open_existing",
            "DurableStateMachine::open_existing",
        ],
    )
    require_tokens(
        DURABLE_MAIN,
''',
        "integrated store lifecycle validator",
    )
    text = replace_once(
        text,
        '''            '"production_selected"',
        ],
''',
        '''            '"production_selected"',
            "DurableStateMachine::open_existing",
            "DurableLogStore::open_existing",
        ],
''',
        "durable main reopen validation",
    )
    VALIDATOR.write_text(text, encoding="utf-8")


def patch_durability_contract() -> None:
    text = DURABILITY.read_text(encoding="utf-8")
    heading = "## 7. Initialized-store lifecycle and rollback-safe replacement"
    if heading in text:
        raise RuntimeError("durability lifecycle section already exists")
    text = text.rstrip() + f'''

{heading}

A durable store has three explicit caller-selected operations:

1. `create-new` creates the first authoritative generation and only then publishes a
   versioned, domain-bound initialization marker;
2. `reopen-existing` requires both a valid marker and a valid authoritative generation;
3. `adopt-legacy` is an explicit migration operation that validates the complete legacy
   envelope, schema and invariants before publishing a marker.

The ordinary reopen path MUST NOT create directories, initialize defaults, adopt legacy
state, or infer that missing files mean a fresh store. Deleting both a marker and its
authoritative generation remains data loss; it does not become an implicit bootstrap
because the caller must still select `reopen-existing`.

Interrupted replacement recovery follows these rules:

- a missing current file plus exactly one `.previous` candidate may recover that candidate;
- multiple previous candidates are ambiguous and fail closed;
- a present current file is validated before any stale previous candidate is removed;
- a corrupt current file never falls back silently to a previous generation;
- one stale previous file may be retired only after current envelope, schema and domain
  invariants validate and the parent directory is synchronized where supported;
- orphan temporary files cannot authorize create-new or legacy adoption.

Tests MUST cover fresh create/reopen, missing generation, deleted directory, explicit
legacy adoption, corrupted marker, stale previous cleanup, corrupt-current no-rollback,
and multiple-previous ambiguity.

These repository-level guarantees do not establish storage-controller cache persistence,
kernel power-cut safety, or filesystem-specific crash consistency. Those require the
separately operated laboratory evidence defined by the external action package.
'''
    DURABILITY.write_text(text, encoding="utf-8")


def main() -> int:
    patch_store()
    patch_cluster()
    patch_durable_main()
    patch_plan()
    patch_register()
    patch_validator()
    patch_durability_contract()
    print("explicit durable lifecycle and initialized-generation guard applied")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
