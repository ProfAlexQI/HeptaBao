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
const STATE_MAGIC: [u8; 8] = *b"HBRSM001";
const SNAPSHOT_MAGIC: [u8; 8] = *b"HBRSNP01";
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
    let length = usize::try_from(length).map_err(|_| invalid("durable envelope length overflow"))?;
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

fn read_payload(path: &Path, magic: [u8; 8]) -> io::Result<Vec<u8>> {
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
    let temporary = parent.join(format!(".{file_name}.{}.{}.tmp", std::process::id(), sequence));
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

#[derive(Debug)]
pub struct DurableLogStore {
    state_path: PathBuf,
    state: Mutex<PersistentLogState>,
}

impl DurableLogStore {
    pub fn open(root: impl AsRef<Path>) -> io::Result<Arc<Self>> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let state_path = root.join("raft-log.bin");
        let state = if state_path.is_file() {
            read_json(&state_path, LOG_MAGIC)?
        } else {
            PersistentLogState::default()
        };
        state.validate()?;
        Ok(Arc::new(Self {
            state_path,
            state: Mutex::new(state),
        }))
    }

    fn persist(&self, state: &PersistentLogState) -> io::Result<()> {
        state.validate()?;
        write_json(&self.state_path, LOG_MAGIC, state)
    }

    pub fn state_path(&self) -> &Path {
        &self.state_path
    }
}

impl RaftLogReader<TypeConfig> for Arc<DurableLogStore> {
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
        Ok(self.state.lock().await.vote.clone())
    }
}

impl RaftLogStorage<TypeConfig> for Arc<DurableLogStore> {
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
        state.vote = Some(vote.clone());
        self.persist(&state)
    }

    async fn save_committed(&mut self, committed: Option<LogIdOf<TypeConfig>>) -> Result<(), io::Error> {
        let mut state = self.state.lock().await;
        state.committed = committed;
        self.persist(&state)
    }

    async fn read_committed(&mut self) -> Result<Option<LogIdOf<TypeConfig>>, io::Error> {
        Ok(self.state.lock().await.committed)
    }

    async fn append<I>(&mut self, entries: I, callback: IOFlushed<TypeConfig>) -> Result<(), io::Error>
    where
        I: IntoIterator<Item = EntryOf<TypeConfig>> + OptionalSend,
        I::IntoIter: OptionalSend,
    {
        let mut state = self.state.lock().await;
        for entry in entries {
            let index = entry.index();
            let serialized =
                serde_json::to_string(&entry).map_err(|error| invalid(error.to_string()))?;
            if let Some(existing) = state.log.get(&index) {
                if existing != &serialized {
                    let error = invalid(format!(
                        "attempted to overwrite log index {index} without truncate"
                    ));
                    callback.io_completed(Err(io::Error::new(error.kind(), error.to_string())));
                    return Err(error);
                }
            } else {
                state.log.insert(index, serialized);
            }
        }
        let result = self.persist(&state);
        match result {
            Ok(()) => {
                callback.io_completed(Ok(()));
                Ok(())
            }
            Err(error) => {
                callback.io_completed(Err(io::Error::new(error.kind(), error.to_string())));
                Err(error)
            }
        }
    }

    async fn truncate_after(&mut self, last_log_id: Option<LogIdOf<TypeConfig>>) -> Result<(), io::Error> {
        let start = match last_log_id {
            Some(log_id) => log_id
                .index
                .checked_add(1)
                .ok_or_else(|| invalid("truncate index overflow"))?,
            None => 0,
        };
        let mut state = self.state.lock().await;
        let remove = state.log.range(start..).map(|(index, _)| *index).collect::<Vec<_>>();
        for index in remove {
            state.log.remove(&index);
        }
        self.persist(&state)
    }

    async fn purge(&mut self, log_id: LogIdOf<TypeConfig>) -> Result<(), io::Error> {
        let mut state = self.state.lock().await;
        if state.last_purged_log_id.is_some_and(|last| last > log_id) {
            return Err(invalid("purge log id regressed"));
        }
        let remove = state
            .log
            .range(..=log_id.index)
            .map(|(index, _)| *index)
            .collect::<Vec<_>>();
        for index in remove {
            state.log.remove(&index);
        }
        state.last_purged_log_id = Some(log_id);
        self.persist(&state)
    }
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct PersistentSnapshot {
    meta: SnapshotMetaOf<TypeConfig>,
    data: Vec<u8>,
}

#[derive(Debug)]
pub struct DurableStateMachine {
    state_path: PathBuf,
    snapshot_path: PathBuf,
    state: Mutex<MemStoreStateMachine>,
    current_snapshot: Mutex<Option<PersistentSnapshot>>,
}

impl DurableStateMachine {
    pub fn open(root: impl AsRef<Path>) -> io::Result<Arc<Self>> {
        let root = root.as_ref();
        fs::create_dir_all(root)?;
        let state_path = root.join("state-machine.bin");
        let snapshot_path = root.join("snapshot.bin");
        let snapshot = if snapshot_path.is_file() {
            Some(read_json::<PersistentSnapshot>(&snapshot_path, SNAPSHOT_MAGIC)?)
        } else {
            None
        };
        let state = if state_path.is_file() {
            read_json(&state_path, STATE_MAGIC)?
        } else if let Some(snapshot) = &snapshot {
            serde_json::from_slice(&snapshot.data).map_err(|error| invalid(error.to_string()))?
        } else {
            MemStoreStateMachine::default()
        };
        let machine = Arc::new(Self {
            state_path,
            snapshot_path,
            state: Mutex::new(state),
            current_snapshot: Mutex::new(snapshot),
        });
        if !machine.state_path.is_file() {
            let state = machine.state.blocking_lock();
            machine.persist_state(&state)?;
        }
        Ok(machine)
    }

    fn persist_state(&self, state: &MemStoreStateMachine) -> io::Result<()> {
        write_json(&self.state_path, STATE_MAGIC, state)
    }

    fn persist_snapshot(&self, snapshot: &PersistentSnapshot) -> io::Result<()> {
        write_json(&self.snapshot_path, SNAPSHOT_MAGIC, snapshot)
    }

    pub async fn get_state_machine(&self) -> MemStoreStateMachine {
        self.state.lock().await.clone()
    }

    pub fn state_path(&self) -> &Path {
        &self.state_path
    }

    pub fn snapshot_path(&self) -> &Path {
        &self.snapshot_path
    }
}

impl RaftSnapshotBuilder<TypeConfig> for Arc<DurableStateMachine> {
    type SnapshotData = Cursor<Vec<u8>>;

    async fn build_snapshot(&mut self) -> Result<SnapshotOf<TypeConfig, Self::SnapshotData>, io::Error> {
        let state = self.state.lock().await.clone();
        let data = serde_json::to_vec(&state).map_err(|error| invalid(error.to_string()))?;
        let meta = SnapshotMetaOf::<TypeConfig> {
            last_log_id: state.last_applied_log,
            last_membership: state.last_membership.clone(),
        };
        let snapshot = PersistentSnapshot {
            meta: meta.clone(),
            data: data.clone(),
        };
        self.persist_snapshot(&snapshot)?;
        *self.current_snapshot.lock().await = Some(snapshot);
        Ok(SnapshotOf::<TypeConfig, Cursor<Vec<u8>>> {
            meta,
            snapshot: Cursor::new(data),
        })
    }
}

impl RaftStateMachine<TypeConfig> for Arc<DurableStateMachine> {
    type SnapshotData = Cursor<Vec<u8>>;
    type SnapshotBuilder = Self;

    async fn applied_state(
        &mut self,
    ) -> Result<(Option<LogIdOf<TypeConfig>>, StoredMembershipOf<TypeConfig>), io::Error> {
        let state = self.state.lock().await;
        Ok((state.last_applied_log, state.last_membership.clone()))
    }

    async fn apply<Strm>(&mut self, mut entries: Strm) -> Result<(), io::Error>
    where
        Strm: Stream<Item = Result<EntryResponder<TypeConfig>, io::Error>> + Unpin + OptionalSend,
    {
        while let Some((entry, responder)) = entries.try_next().await? {
            let response = {
                let mut state = self.state.lock().await;
                state.last_applied_log = Some(entry.log_id);
                let response = match entry.payload {
                    EntryPayload::Blank => ClientResponse(None),
                    EntryPayload::Normal(ref data) => {
                        let previous = state
                            .client_status
                            .insert(data.client.clone(), data.status.clone());
                        ClientResponse(previous)
                    }
                    EntryPayload::Membership(ref membership) => {
                        state.last_membership = StoredMembershipOf::<TypeConfig>::new(
                            Some(entry.log_id),
                            membership.clone(),
                        );
                        ClientResponse(None)
                    }
                };
                self.persist_state(&state)?;
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
        let state_membership =
            serde_json::to_vec(&state.last_membership).map_err(|error| invalid(error.to_string()))?;
        let meta_membership =
            serde_json::to_vec(&meta.last_membership).map_err(|error| invalid(error.to_string()))?;
        if state_membership != meta_membership {
            return Err(invalid("snapshot membership does not match metadata"));
        }
        let persisted = PersistentSnapshot {
            meta: meta.clone(),
            data,
        };
        self.persist_state(&state)?;
        self.persist_snapshot(&persisted)?;
        *self.state.lock().await = state;
        *self.current_snapshot.lock().await = Some(persisted);
        Ok(())
    }

    async fn get_current_snapshot(
        &mut self,
    ) -> Result<Option<SnapshotOf<TypeConfig, Self::SnapshotData>>, io::Error> {
        Ok(self.current_snapshot.lock().await.clone().map(|snapshot| {
            SnapshotOf::<TypeConfig, Cursor<Vec<u8>>> {
                meta: snapshot.meta,
                snapshot: Cursor::new(snapshot.data),
            }
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
