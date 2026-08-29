use std::collections::BTreeMap;
use std::fmt::Debug;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Cursor, Read, Write};
use std::ops::RangeBounds;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::sync::atomic::{AtomicU64, Ordering};

use futures::{Stream, TryStreamExt};
use openraft::alias::{EntryOf, LogIdOf, SnapshotMetaOf, SnapshotOf, StoredMembershipOf, VoteOf};
use openraft::entry::RaftEntry;
use openraft::storage::{
    EntryResponder, IOFlushed, LogState, RaftLogReader, RaftLogStorage, RaftSnapshotBuilder,
    RaftStateMachine,
};
use openraft::{EntryPayload, OptionalSend};
use openraft_memstore::{ClientResponse, MemStoreStateMachine, TypeConfig};
use serde::{Deserialize, Serialize};
use tokio::sync::Mutex;

const LOG_MAGIC: [u8; 8] = *b"HBRLOG01";
const STATE_BUNDLE_MAGIC: [u8; 8] = *b"HBRSB001";
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn invalid(message: impl Into<String>) -> io::Error {
    io::Error::new(io::ErrorKind::InvalidData, message.into())
}

fn crc32(bytes: &[u8]) -> u32 {
    let mut crc = 0xffff_ffff_u32;
    for byte in bytes {
        crc ^= u32::from(*byte);
        for _ in 0..8 {
            let mask = 0_u32.wrapping_sub(crc & 1);
            crc = (crc >> 1) ^ (0xedb8_8320 & mask);
        }
    }
    !crc
}

fn encode_envelope(magic: [u8; 8], payload: &[u8]) -> io::Result<Vec<u8>> {
    let length = u64::try_from(payload.len()).map_err(|_| invalid("payload length overflow"))?;
    let mut encoded = Vec::with_capacity(8 + 8 + payload.len() + 4);
    encoded.extend_from_slice(&magic);
    encoded.extend_from_slice(&length.to_le_bytes());
    encoded.extend_from_slice(payload);
    encoded.extend_from_slice(&crc32(payload).to_le_bytes());
    Ok(encoded)
}

fn decode_envelope(magic: [u8; 8], bytes: &[u8]) -> io::Result<Vec<u8>> {
    if bytes.len() < 20 {
        return Err(invalid("durable envelope is truncated"));
    }
    if bytes[..8] != magic {
        return Err(invalid("durable envelope magic mismatch"));
    }
    let length = u64::from_le_bytes(
        bytes[8..16]
            .try_into()
            .map_err(|_| invalid("invalid durable envelope length field"))?,
    );
    let length =
        usize::try_from(length).map_err(|_| invalid("durable envelope length overflow"))?;
    let expected = 8_usize
        .checked_add(8)
        .and_then(|value| value.checked_add(length))
        .and_then(|value| value.checked_add(4))
        .ok_or_else(|| invalid("durable envelope size overflow"))?;
    if bytes.len() != expected {
        return Err(invalid(format!(
            "durable envelope length mismatch: expected {expected}, got {}",
            bytes.len()
        )));
    }
    let payload = &bytes[16..16 + length];
    let stored_crc = u32::from_le_bytes(
        bytes[16 + length..expected]
            .try_into()
            .map_err(|_| invalid("invalid durable envelope checksum field"))?,
    );
    let actual_crc = crc32(payload);
    if stored_crc != actual_crc {
        return Err(invalid(format!(
            "durable envelope checksum mismatch: stored {stored_crc:08x}, actual {actual_crc:08x}"
        )));
    }
    Ok(payload.to_vec())
}

fn recover_interrupted_replace(path: &Path) -> io::Result<()> {
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

fn read_payload(path: &Path, magic: [u8; 8]) -> io::Result<Vec<u8>> {
    recover_interrupted_replace(path)?;
    let mut file = File::open(path)?;
    let metadata = file.metadata()?;
    if metadata.len() > 128 * 1024 * 1024 {
        return Err(invalid("durable artifact exceeds 128 MiB safety bound"));
    }
    let mut bytes = Vec::with_capacity(usize::try_from(metadata.len()).unwrap_or(0));
    file.read_to_end(&mut bytes)?;
    decode_envelope(magic, &bytes)
}

fn sync_parent(path: &Path) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid(format!("{} has no parent directory", path.display())))?;
    #[cfg(unix)]
    {
        File::open(parent)?.sync_all()?;
    }
    #[cfg(not(unix))]
    {
        let _ = parent;
    }
    Ok(())
}

fn atomic_write(path: &Path, magic: [u8; 8], payload: &[u8]) -> io::Result<()> {
    let parent = path
        .parent()
        .ok_or_else(|| invalid(format!("{} has no parent directory", path.display())))?;
    fs::create_dir_all(parent)?;
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let file_name = path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or_else(|| invalid("durable file name is not valid UTF-8"))?;
    let temporary = parent.join(format!(
        ".{file_name}.{}.{}.tmp",
        std::process::id(),
        sequence
    ));
    let encoded = encode_envelope(magic, payload)?;

    let result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .create_new(true)
            .write(true)
            .open(&temporary)?;
        file.write_all(&encoded)?;
        file.flush()?;
        file.sync_all()?;
        drop(file);

        #[cfg(windows)]
        if path.exists() {
            let previous = parent.join(format!(
                ".{file_name}.{}.{}.previous",
                std::process::id(),
                sequence
            ));
            fs::rename(path, &previous)?;
            if let Err(error) = fs::rename(&temporary, path) {
                let _ = fs::rename(&previous, path);
                return Err(error);
            }
            let _ = fs::remove_file(previous);
        } else {
            fs::rename(&temporary, path)?;
        }

        #[cfg(not(windows))]
        fs::rename(&temporary, path)?;

        sync_parent(path)?;
        Ok(())
    })();

    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn read_json<T>(path: &Path, magic: [u8; 8]) -> io::Result<T>
where
    T: for<'de> Deserialize<'de>,
{
    let payload = read_payload(path, magic)?;
    serde_json::from_slice(&payload).map_err(|error| invalid(error.to_string()))
}

fn write_json<T>(path: &Path, magic: [u8; 8], value: &T) -> io::Result<()>
where
    T: Serialize,
{
    let payload = serde_json::to_vec(value).map_err(|error| invalid(error.to_string()))?;
    atomic_write(path, magic, &payload)
}

#[derive(Clone, Debug, Default, Deserialize, Serialize)]
struct PersistentLogState {
    last_purged_log_id: Option<LogIdOf<TypeConfig>>,
    committed: Option<LogIdOf<TypeConfig>>,
    vote: Option<VoteOf<TypeConfig>>,
    log: BTreeMap<u64, String>,
}

impl PersistentLogState {
    fn validate(&self) -> io::Result<()> {
        let mut previous = self.last_purged_log_id.as_ref().map(|log_id| log_id.index);
        for index in self.log.keys().copied() {
            if let Some(previous) = previous {
                let expected = previous
                    .checked_add(1)
                    .ok_or_else(|| invalid("log index overflow while validating continuity"))?;
                if index != expected {
                    return Err(invalid(format!(
                        "log hole detected: expected index {expected}, observed {index}"
                    )));
                }
            }
            previous = Some(index);
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct DurableLogStore {
    state_path: PathBuf,
    state: Arc<Mutex<PersistentLogState>>,
}

impl DurableLogStore {
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
        state.validate()?;
        write_json(&self.state_path, LOG_MAGIC, state)
    }

    pub fn state_path(&self) -> &Path {
        &self.state_path
    }
}

impl RaftLogReader<TypeConfig> for DurableLogStore {
    async fn try_get_log_entries<RB: RangeBounds<u64> + Clone + Debug + OptionalSend>(
        &mut self,
        range: RB,
    ) -> Result<Vec<EntryOf<TypeConfig>>, io::Error> {
        let state = self.state.lock().await;
        let serialized = state
            .log
            .range(range)
            .map(|(_, value)| value.clone())
            .collect::<Vec<_>>();
        serialized
            .into_iter()
            .map(|value| serde_json::from_str(&value).map_err(|error| invalid(error.to_string())))
            .collect()
    }

    async fn read_vote(&mut self) -> Result<Option<VoteOf<TypeConfig>>, io::Error> {
        Ok(self.state.lock().await.vote)
    }
}

impl RaftLogStorage<TypeConfig> for DurableLogStore {
    type LogReader = Self;

    async fn get_log_state(&mut self) -> Result<LogState<TypeConfig>, io::Error> {
        let state = self.state.lock().await;
        let last_log_id = match state.log.iter().next_back() {
            Some((_, serialized)) => {
                let entry: EntryOf<TypeConfig> =
                    serde_json::from_str(serialized).map_err(|error| invalid(error.to_string()))?;
                Some(entry.log_id())
            }
            None => state.last_purged_log_id,
        };
        Ok(LogState {
            last_purged_log_id: state.last_purged_log_id,
            last_log_id,
        })
    }

    async fn get_log_reader(&mut self) -> Self::LogReader {
        self.clone()
    }

    async fn save_vote(&mut self, vote: &VoteOf<TypeConfig>) -> Result<(), io::Error> {
        let mut state = self.state.lock().await;
        let mut candidate = state.clone();
        candidate.vote = Some(*vote);
        self.persist(&candidate)?;
        *state = candidate;
        Ok(())
    }

    async fn save_committed(
        &mut self,
        committed: Option<LogIdOf<TypeConfig>>,
    ) -> Result<(), io::Error> {
        let mut state = self.state.lock().await;
        let mut candidate = state.clone();
        candidate.committed = committed;
        self.persist(&candidate)?;
        *state = candidate;
        Ok(())
    }

    async fn read_committed(&mut self) -> Result<Option<LogIdOf<TypeConfig>>, io::Error> {
        Ok(self.state.lock().await.committed)
    }

    async fn append<I>(
        &mut self,
        entries: I,
        callback: IOFlushed<TypeConfig>,
    ) -> Result<(), io::Error>
    where
        I: IntoIterator<Item = EntryOf<TypeConfig>> + OptionalSend,
        I::IntoIter: OptionalSend,
    {
        let mut state = self.state.lock().await;
        let mut candidate = state.clone();
        for entry in entries {
            let index = entry.index();
            let serialized =
                serde_json::to_string(&entry).map_err(|error| invalid(error.to_string()))?;
            if let Some(existing) = candidate.log.get(&index) {
                if existing != &serialized {
                    let error = invalid(format!(
                        "attempted to overwrite log index {index} without truncate"
                    ));
                    callback.io_completed(Err(io::Error::new(error.kind(), error.to_string())));
                    return Err(error);
                }
            } else {
                candidate.log.insert(index, serialized);
            }
        }
        match self.persist(&candidate) {
            Ok(()) => {
                *state = candidate;
                callback.io_completed(Ok(()));
                Ok(())
            }
            Err(error) => {
                callback.io_completed(Err(io::Error::new(error.kind(), error.to_string())));
                Err(error)
            }
        }
    }

    async fn truncate_after(
        &mut self,
        last_log_id: Option<LogIdOf<TypeConfig>>,
    ) -> Result<(), io::Error> {
        let start = match last_log_id {
            Some(log_id) => log_id
                .index
                .checked_add(1)
                .ok_or_else(|| invalid("truncate index overflow"))?,
            None => 0,
        };
        let mut state = self.state.lock().await;
        let mut candidate = state.clone();
        let remove = candidate
            .log
            .range(start..)
            .map(|(index, _)| *index)
            .collect::<Vec<_>>();
        for index in remove {
            candidate.log.remove(&index);
        }
        self.persist(&candidate)?;
        *state = candidate;
        Ok(())
    }

    async fn purge(&mut self, log_id: LogIdOf<TypeConfig>) -> Result<(), io::Error> {
        let mut state = self.state.lock().await;
        let mut candidate = state.clone();
        if candidate.last_purged_log_id.is_some_and(|last| last > log_id) {
            return Err(invalid("purge log id regressed"));
        }
        let remove = candidate
            .log
            .range(..=log_id.index)
            .map(|(index, _)| *index)
            .collect::<Vec<_>>();
        for index in remove {
            candidate.log.remove(&index);
        }
        candidate.last_purged_log_id = Some(log_id);
        self.persist(&candidate)?;
        *state = candidate;
        Ok(())
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct PersistentSnapshot {
    meta: SnapshotMetaOf<TypeConfig>,
    data: Vec<u8>,
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct PersistentStateBundle {
    format_version: u16,
    generation: u64,
    state: MemStoreStateMachine,
    current_snapshot: Option<PersistentSnapshot>,
}

impl Default for PersistentStateBundle {
    fn default() -> Self {
        Self {
            format_version: 1,
            generation: 1,
            state: MemStoreStateMachine::default(),
            current_snapshot: None,
        }
    }
}

impl PersistentStateBundle {
    fn next_generation(&self) -> io::Result<u64> {
        self.generation
            .checked_add(1)
            .ok_or_else(|| invalid("state bundle generation overflow"))
    }

    fn validate(&self) -> io::Result<()> {
        if self.format_version != 1 || self.generation == 0 {
            return Err(invalid("unsupported or zero state bundle generation"));
        }
        if let Some(snapshot) = &self.current_snapshot {
            let snapshot_state: MemStoreStateMachine = serde_json::from_slice(&snapshot.data)
                .map_err(|error| invalid(error.to_string()))?;
            if snapshot_state.last_applied_log != snapshot.meta.last_log_id {
                return Err(invalid("snapshot state and metadata last-applied mismatch"));
            }
            let state_membership = serde_json::to_vec(&snapshot_state.last_membership)
                .map_err(|error| invalid(error.to_string()))?;
            let meta_membership = serde_json::to_vec(&snapshot.meta.last_membership)
                .map_err(|error| invalid(error.to_string()))?;
            if state_membership != meta_membership {
                return Err(invalid("snapshot state and metadata membership mismatch"));
            }
        }
        Ok(())
    }
}

#[derive(Clone, Debug)]
pub struct DurableStateMachine {
    bundle_path: PathBuf,
    bundle: Arc<Mutex<PersistentStateBundle>>,
}

impl DurableStateMachine {
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
        bundle.validate()?;
        write_json(&self.bundle_path, STATE_BUNDLE_MAGIC, bundle)
    }

    pub async fn get_state_machine(&self) -> MemStoreStateMachine {
        self.bundle.lock().await.state.clone()
    }

    pub async fn has_current_snapshot(&self) -> bool {
        self.bundle.lock().await.current_snapshot.is_some()
    }

    pub async fn generation(&self) -> u64 {
        self.bundle.lock().await.generation
    }

    pub fn state_path(&self) -> &Path {
        &self.bundle_path
    }

    pub fn snapshot_path(&self) -> &Path {
        &self.bundle_path
    }
}

impl RaftSnapshotBuilder<TypeConfig> for DurableStateMachine {
    type SnapshotData = Cursor<Vec<u8>>;

    async fn build_snapshot(
        &mut self,
    ) -> Result<SnapshotOf<TypeConfig, Self::SnapshotData>, io::Error> {
        let mut bundle = self.bundle.lock().await;
        let state = bundle.state.clone();
        let data = serde_json::to_vec(&state).map_err(|error| invalid(error.to_string()))?;
        let meta = SnapshotMetaOf::<TypeConfig> {
            last_log_id: state.last_applied_log,
            last_membership: state.last_membership.clone(),
        };
        let snapshot = PersistentSnapshot {
            meta: meta.clone(),
            data: data.clone(),
        };
        let mut candidate = bundle.clone();
        candidate.generation = candidate.next_generation()?;
        candidate.current_snapshot = Some(snapshot);
        self.persist_bundle(&candidate)?;
        *bundle = candidate;
        Ok(SnapshotOf::<TypeConfig, Cursor<Vec<u8>>> {
            meta,
            snapshot: Cursor::new(data),
        })
    }
}

impl RaftStateMachine<TypeConfig> for DurableStateMachine {
    type SnapshotData = Cursor<Vec<u8>>;
    type SnapshotBuilder = Self;

    async fn applied_state(
        &mut self,
    ) -> Result<(Option<LogIdOf<TypeConfig>>, StoredMembershipOf<TypeConfig>), io::Error> {
        let bundle = self.bundle.lock().await;
        Ok((
            bundle.state.last_applied_log,
            bundle.state.last_membership.clone(),
        ))
    }

    async fn apply<Strm>(&mut self, mut entries: Strm) -> Result<(), io::Error>
    where
        Strm: Stream<Item = Result<EntryResponder<TypeConfig>, io::Error>> + Unpin + OptionalSend,
    {
        while let Some((entry, responder)) = entries.try_next().await? {
            let response = {
                let mut bundle = self.bundle.lock().await;
                let mut candidate = bundle.clone();
                candidate.generation = candidate.next_generation()?;
                candidate.state.last_applied_log = Some(entry.log_id);
                let response = match entry.payload {
                    EntryPayload::Blank => ClientResponse(None),
                    EntryPayload::Normal(ref data) => {
                        let previous = candidate
                            .state
                            .client_status
                            .insert(data.client.clone(), data.status.clone());
                        ClientResponse(previous)
                    }
                    EntryPayload::Membership(ref membership) => {
                        candidate.state.last_membership = StoredMembershipOf::<TypeConfig>::new(
                            Some(entry.log_id),
                            membership.clone(),
                        );
                        ClientResponse(None)
                    }
                };
                self.persist_bundle(&candidate)?;
                *bundle = candidate;
                response
            };
            if let Some(responder) = responder {
                responder.send(response);
            }
        }
        Ok(())
    }

    async fn try_create_snapshot_builder(&mut self, _force: bool) -> Option<Self::SnapshotBuilder> {
        Some(self.clone())
    }

    async fn get_snapshot_builder(&mut self) -> Self::SnapshotBuilder {
        self.clone()
    }

    async fn install_snapshot(
        &mut self,
        meta: &SnapshotMetaOf<TypeConfig>,
        snapshot: Self::SnapshotData,
    ) -> Result<(), io::Error> {
        let data = snapshot.into_inner();
        let state: MemStoreStateMachine =
            serde_json::from_slice(&data).map_err(|error| invalid(error.to_string()))?;
        if state.last_applied_log != meta.last_log_id {
            return Err(invalid("snapshot last-applied log does not match metadata"));
        }
        let state_membership = serde_json::to_vec(&state.last_membership)
            .map_err(|error| invalid(error.to_string()))?;
        let meta_membership = serde_json::to_vec(&meta.last_membership)
            .map_err(|error| invalid(error.to_string()))?;
        if state_membership != meta_membership {
            return Err(invalid("snapshot membership does not match metadata"));
        }
        let persisted = PersistentSnapshot {
            meta: meta.clone(),
            data,
        };
        let mut bundle = self.bundle.lock().await;
        let mut candidate = bundle.clone();
        candidate.generation = candidate.next_generation()?;
        candidate.state = state;
        candidate.current_snapshot = Some(persisted);
        self.persist_bundle(&candidate)?;
        *bundle = candidate;
        Ok(())
    }

    async fn get_current_snapshot(
        &mut self,
    ) -> Result<Option<SnapshotOf<TypeConfig, Self::SnapshotData>>, io::Error> {
        Ok(self
            .bundle
            .lock()
            .await
            .current_snapshot
            .clone()
            .map(|snapshot| SnapshotOf::<TypeConfig, Cursor<Vec<u8>>> {
                meta: snapshot.meta,
                snapshot: Cursor::new(snapshot.data),
            }))
    }
}

pub fn flip_first_payload_byte(path: &Path) -> io::Result<()> {
    let mut bytes = fs::read(path)?;
    if bytes.len() <= 20 {
        return Err(invalid("cannot corrupt an empty durable envelope"));
    }
    bytes[16] ^= 0x80;
    fs::write(path, bytes)?;
    File::open(path)?.sync_all()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        DurableLogStore, DurableStateMachine, LOG_MAGIC, PersistentLogState,
        PersistentStateBundle, RaftLogStorage, RaftSnapshotBuilder, STATE_BUNDLE_MAGIC, read_json,
        write_json,
    };
    use std::collections::BTreeMap;
    use std::fs;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicU64, Ordering};
    use tokio::sync::Mutex;

    static TEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

    fn root(label: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!(
            "heptabao-{label}-{}-{}",
            std::process::id(),
            TEST_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ))
    }

    #[tokio::test]
    async fn failed_log_persist_does_not_publish_candidate_state() {
        let root = root("log-persist-failure");
        fs::create_dir_all(&root).expect("test root");
        let blocking_parent = root.join("not-a-directory");
        fs::write(&blocking_parent, b"block").expect("blocking file");
        let mut log = BTreeMap::new();
        log.insert(1, "synthetic-entry".to_owned());
        let state = PersistentLogState {
            log,
            ..PersistentLogState::default()
        };
        let mut store = DurableLogStore {
            state_path: blocking_parent.join("raft-log.bin"),
            state: Arc::new(Mutex::new(state)),
        };

        let result = store.truncate_after(None).await;
        assert!(result.is_err());
        assert!(store.state.lock().await.log.contains_key(&1));
        let _ = fs::remove_dir_all(root);
    }

    #[tokio::test]
    async fn failed_snapshot_persist_does_not_publish_snapshot_or_generation() {
        let root = root("snapshot-persist-failure");
        fs::create_dir_all(&root).expect("test root");
        let blocking_parent = root.join("not-a-directory");
        fs::write(&blocking_parent, b"block").expect("blocking file");
        let initial = PersistentStateBundle::default();
        let mut state_machine = DurableStateMachine {
            bundle_path: blocking_parent.join("state-bundle.bin"),
            bundle: Arc::new(Mutex::new(initial)),
        };

        let result = state_machine.build_snapshot().await;
        assert!(result.is_err());
        let bundle = state_machine.bundle.lock().await;
        assert_eq!(bundle.generation, 1);
        assert!(bundle.current_snapshot.is_none());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn interrupted_previous_file_is_recovered_fail_closed() {
        let root = root("replace-recovery");
        fs::create_dir_all(&root).expect("test root");
        let target = root.join("state-bundle.bin");
        let previous = root.join(".state-bundle.bin.1.1.previous");
        let expected = PersistentStateBundle::default();
        write_json(&previous, STATE_BUNDLE_MAGIC, &expected).expect("write previous");

        let recovered: PersistentStateBundle =
            read_json(&target, STATE_BUNDLE_MAGIC).expect("recover previous");
        assert_eq!(recovered.generation, expected.generation);
        assert!(target.is_file());
        assert!(!previous.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn log_envelope_round_trip_remains_bounded() {
        let root = root("log-roundtrip");
        fs::create_dir_all(&root).expect("test root");
        let path = root.join("raft-log.bin");
        let expected = PersistentLogState::default();
        write_json(&path, LOG_MAGIC, &expected).expect("write log");
        let _: PersistentLogState = read_json(&path, LOG_MAGIC).expect("read log");
        let _ = fs::remove_dir_all(root);
    }
}
