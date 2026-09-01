#![forbid(unsafe_code)]
#![deny(missing_debug_implementations)]

//! Fail-closed single-process durable generation store.
//!
//! This implementation is a development foundation for exercising explicit
//! create/reopen/adopt lifecycle, immutable generation bundles, compare-and-
//! swap commits and persist-before-publish ordering. It is not a multi-process
//! store, does not provide rollback protection outside its directory and has no
//! production authority.

use std::error::Error;
use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};

use heptabao_storage_api::{
    CommitReceipt, DurableGenerationStore, Generation, GenerationSnapshot, IntegrityProvider,
    OpaqueState, StateDigest, StorageContractError, StoreDomain, StoreOpenMode,
};

const MARKER_NAME: &str = "heptabao.marker";
const CURRENT_NAME: &str = "CURRENT";
const MARKER_MAGIC: &[u8; 25] = b"HEPTABAO-STORE-MARKER-V1\0";
const CURRENT_MAGIC: &[u8; 20] = b"HEPTABAO-CURRENT-V1\0";
const BUNDLE_MAGIC: &[u8; 19] = b"HEPTABAO-BUNDLE-V1\0";
const MAX_CONTROL_FILE_BYTES: usize = 64 * 1024;
const BUNDLE_OVERHEAD_BOUND: usize = 64 * 1024;

static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);

pub struct FileGenerationStore<P: IntegrityProvider> {
    root: PathBuf,
    domain: StoreDomain,
    integrity: P,
    open_mode: StoreOpenMode,
    current: Option<Generation>,
}

impl<P: IntegrityProvider> fmt::Debug for FileGenerationStore<P> {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("FileGenerationStore")
            .field("root", &"[REDACTED_ABSOLUTE_PATH]")
            .field("domain", &self.domain)
            .field("integrity_algorithm", &self.integrity.algorithm_id())
            .field("open_mode", &self.open_mode)
            .field("current", &self.current)
            .finish()
    }
}

impl<P: IntegrityProvider> FileGenerationStore<P> {
    pub fn create_new(
        root: impl AsRef<Path>,
        domain: StoreDomain,
        integrity: P,
    ) -> Result<Self, FileStoreError<P::Error>> {
        let root = root.as_ref().to_path_buf();
        validate_root(&root)?;
        if !directory_is_empty(&root)? {
            return Err(FileStoreError::DirectoryNotEmpty);
        }
        Ok(Self {
            root,
            domain,
            integrity,
            open_mode: StoreOpenMode::CreateNew,
            current: None,
        })
    }

    pub fn reopen_existing(
        root: impl AsRef<Path>,
        domain: StoreDomain,
        integrity: P,
    ) -> Result<Self, FileStoreError<P::Error>> {
        let root = root.as_ref().to_path_buf();
        validate_root(&root)?;
        let mut store = Self {
            root,
            domain,
            integrity,
            open_mode: StoreOpenMode::ReopenExisting,
            current: None,
        };
        store.validate_marker()?;
        let record = store.read_current_record()?;
        let bundle = store.read_and_verify_bundle(record.generation)?;
        if bundle.digest != record.digest {
            return Err(FileStoreError::CorruptState);
        }
        store.current = Some(record.generation);
        Ok(store)
    }

    pub fn adopt_legacy(
        root: impl AsRef<Path>,
        domain: StoreDomain,
        integrity: P,
    ) -> Result<Self, FileStoreError<P::Error>> {
        let root = root.as_ref().to_path_buf();
        validate_root(&root)?;
        reject_unresolved_temporary_artifacts(&root)?;
        let marker_path = root.join(MARKER_NAME);
        match fs::symlink_metadata(&marker_path) {
            Ok(_) => return Err(FileStoreError::AlreadyInitialized),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(FileStoreError::Io(error)),
        }

        let mut store = Self {
            root,
            domain,
            integrity,
            open_mode: StoreOpenMode::AdoptLegacy,
            current: None,
        };
        let record = store.read_current_record()?;
        let bundle = store.read_and_verify_bundle(record.generation)?;
        if bundle.digest != record.digest {
            return Err(FileStoreError::CorruptState);
        }
        store.publish_marker().map_err(|error| match error {
            FileStoreError::Io(io_error) => FileStoreError::Io(io_error),
            other => other,
        })?;
        store.current = Some(record.generation);
        Ok(store)
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    fn ensure_disk_matches_memory(&self) -> Result<(), FileStoreError<P::Error>> {
        validate_root(&self.root)?;
        match self.current {
            None => {
                if !directory_is_empty(&self.root)? {
                    return Err(FileStoreError::UnexpectedInitializedState);
                }
                Ok(())
            }
            Some(expected) => {
                self.validate_marker()?;
                let record = self.read_current_record()?;
                if record.generation != expected {
                    return Err(FileStoreError::GenerationConflict {
                        expected: Some(expected),
                        actual: Some(record.generation),
                    });
                }
                let bundle = self.read_and_verify_bundle(record.generation)?;
                if bundle.digest != record.digest {
                    return Err(FileStoreError::CorruptState);
                }
                Ok(())
            }
        }
    }

    fn marker_path(&self) -> PathBuf {
        self.root.join(MARKER_NAME)
    }

    fn current_path(&self) -> PathBuf {
        self.root.join(CURRENT_NAME)
    }

    fn bundle_path(&self, generation: Generation) -> PathBuf {
        self.root.join(bundle_file_name(generation))
    }

    fn validate_marker(&self) -> Result<(), FileStoreError<P::Error>> {
        let bytes = read_regular_file(&self.marker_path(), MAX_CONTROL_FILE_BYTES)
            .map_err(map_marker_read_error)?;
        let decoded = decode_marker(&bytes).map_err(|_| FileStoreError::MarkerMismatch)?;
        if decoded.domain != self.domain.as_str()
            || decoded.integrity_algorithm != self.integrity.algorithm_id().as_str()
        {
            return Err(FileStoreError::MarkerMismatch);
        }
        Ok(())
    }

    fn publish_marker(&self) -> Result<(), FileStoreError<P::Error>> {
        let mut bytes =
            encode_marker(self.domain.as_str(), self.integrity.algorithm_id().as_str())?;
        let result = atomic_replace(&self.root, MARKER_NAME, &bytes);
        bytes.fill(0);
        match result {
            Ok(()) => Ok(()),
            Err(error) => Err(FileStoreError::Io(error.source)),
        }
    }

    fn read_current_record(&self) -> Result<CurrentRecord, FileStoreError<P::Error>> {
        let bytes = read_regular_file(&self.current_path(), MAX_CONTROL_FILE_BYTES)
            .map_err(map_current_read_error)?;
        decode_current(&bytes).map_err(|_| FileStoreError::CorruptState)
    }

    fn read_and_verify_bundle(
        &self,
        generation: Generation,
    ) -> Result<DecodedBundle, FileStoreError<P::Error>> {
        let maximum = heptabao_storage_api::MAX_OPAQUE_STATE_BYTES
            .checked_add(BUNDLE_OVERHEAD_BOUND)
            .ok_or(FileStoreError::CorruptState)?;
        let bytes = read_regular_file(&self.bundle_path(generation), maximum)?;
        let mut bundle = decode_bundle(&bytes).map_err(|_| FileStoreError::CorruptState)?;
        if bundle.generation != generation
            || bundle.domain != self.domain.as_str()
            || bundle.integrity_algorithm != self.integrity.algorithm_id().as_str()
        {
            return Err(FileStoreError::CorruptState);
        }
        let digest = match self
            .integrity
            .digest(&self.domain, generation, &bundle.state)
        {
            Ok(value) => value,
            Err(error) => {
                bundle.state.fill(0);
                return Err(FileStoreError::IntegrityProvider(error));
            }
        };
        if digest != bundle.digest {
            return Err(FileStoreError::CorruptState);
        }
        Ok(bundle)
    }
}

impl<P> DurableGenerationStore for FileGenerationStore<P>
where
    P: IntegrityProvider,
{
    type Error = FileStoreError<P::Error>;

    fn domain(&self) -> &StoreDomain {
        &self.domain
    }

    fn open_mode(&self) -> StoreOpenMode {
        self.open_mode
    }

    fn current_generation(&self) -> Option<Generation> {
        self.current
    }

    fn load_current(&self) -> Result<Option<GenerationSnapshot>, Self::Error> {
        self.ensure_disk_matches_memory()?;
        let Some(generation) = self.current else {
            return Ok(None);
        };
        let record = self.read_current_record()?;
        let bundle = self.read_and_verify_bundle(generation)?;
        if bundle.digest != record.digest {
            return Err(FileStoreError::CorruptState);
        }
        let digest = bundle.digest;
        let state = OpaqueState::new(bundle.into_state()).map_err(FileStoreError::Contract)?;
        Ok(Some(GenerationSnapshot {
            generation,
            digest,
            state,
        }))
    }

    fn commit(
        &mut self,
        expected_current: Option<Generation>,
        candidate: OpaqueState,
    ) -> Result<CommitReceipt, Self::Error> {
        self.ensure_disk_matches_memory()?;
        if expected_current != self.current {
            return Err(FileStoreError::GenerationConflict {
                expected: expected_current,
                actual: self.current,
            });
        }
        let previous = self.current;
        let generation = match previous {
            Some(value) => value.checked_next().map_err(FileStoreError::Contract)?,
            None => Generation::INITIAL,
        };
        let digest = self
            .integrity
            .digest(&self.domain, generation, candidate.as_bytes())
            .map_err(FileStoreError::IntegrityProvider)?;

        let bundle_path = self.bundle_path(generation);
        match fs::symlink_metadata(&bundle_path) {
            Ok(_) => return Err(FileStoreError::GenerationAlreadyExists(generation)),
            Err(error) if error.kind() == io::ErrorKind::NotFound => {}
            Err(error) => return Err(FileStoreError::Io(error)),
        }

        let mut bundle_bytes = encode_bundle(
            generation,
            self.domain.as_str(),
            self.integrity.algorithm_id().as_str(),
            digest,
            candidate.as_bytes(),
        )?;
        let bundle_result = write_new_file_and_sync_parent(&bundle_path, &bundle_bytes);
        bundle_bytes.fill(0);
        bundle_result?;

        let mut current_bytes = encode_current(CurrentRecord { generation, digest });
        let current_result = atomic_replace(&self.root, CURRENT_NAME, &current_bytes);
        current_bytes.fill(0);
        if let Err(error) = current_result {
            if error.published {
                return Err(FileStoreError::CommitOutcomeUnknown);
            }
            return Err(FileStoreError::Io(error.source));
        }

        if previous.is_none() && self.publish_marker().is_err() {
            return Err(FileStoreError::CommitOutcomeUnknown);
        }

        let verified_record = self
            .read_current_record()
            .map_err(|_| FileStoreError::CommitOutcomeUnknown)?;
        let verified_bundle = self
            .read_and_verify_bundle(generation)
            .map_err(|_| FileStoreError::CommitOutcomeUnknown)?;
        if verified_record.generation != generation
            || verified_record.digest != digest
            || verified_bundle.digest != digest
        {
            return Err(FileStoreError::CommitOutcomeUnknown);
        }

        self.current = Some(generation);
        Ok(CommitReceipt {
            previous,
            committed: generation,
            digest,
        })
    }
}

#[derive(Debug)]
pub enum FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    Contract(StorageContractError),
    IntegrityProvider(E),
    Io(io::Error),
    RootMustBeAbsolute,
    UnsafeRoot,
    DirectoryNotEmpty,
    AlreadyInitialized,
    UnexpectedInitializedState,
    MarkerMissing,
    MarkerMismatch,
    CurrentMissing,
    UnsafeFileType,
    CorruptState,
    GenerationAlreadyExists(Generation),
    GenerationConflict {
        expected: Option<Generation>,
        actual: Option<Generation>,
    },
    CommitOutcomeUnknown,
}

impl<E> fmt::Display for FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Contract(error) => write!(formatter, "storage contract failure: {error}"),
            Self::IntegrityProvider(error) => {
                write!(formatter, "integrity provider failure: {error}")
            }
            Self::Io(error) => write!(formatter, "storage I/O failure: {error}"),
            Self::RootMustBeAbsolute => formatter.write_str("storage root must be absolute"),
            Self::UnsafeRoot => formatter.write_str("storage root path is unsafe"),
            Self::DirectoryNotEmpty => formatter.write_str("create-new storage root must be empty"),
            Self::AlreadyInitialized => formatter.write_str("storage root is already initialized"),
            Self::UnexpectedInitializedState => {
                formatter.write_str("storage root changed after create-new open")
            }
            Self::MarkerMissing => formatter.write_str("initialized-store marker is missing"),
            Self::MarkerMismatch => formatter.write_str("initialized-store marker is invalid"),
            Self::CurrentMissing => formatter.write_str("CURRENT generation pointer is missing"),
            Self::UnsafeFileType => formatter.write_str("storage path is not a regular file"),
            Self::CorruptState => formatter.write_str("durable generation state is corrupt"),
            Self::GenerationAlreadyExists(generation) => {
                write!(formatter, "generation {} already exists", generation.get())
            }
            Self::GenerationConflict { expected, actual } => write!(
                formatter,
                "generation compare-and-swap conflict: expected {expected:?}, actual {actual:?}"
            ),
            Self::CommitOutcomeUnknown => formatter.write_str(
                "durable publication may have occurred; reconcile before retrying the mutation",
            ),
        }
    }
}

impl<E> Error for FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    fn source(&self) -> Option<&(dyn Error + 'static)> {
        match self {
            Self::Contract(error) => Some(error),
            Self::IntegrityProvider(error) => Some(error),
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl<E> From<StorageContractError> for FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    fn from(error: StorageContractError) -> Self {
        Self::Contract(error)
    }
}

impl<E> From<io::Error> for FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct CurrentRecord {
    generation: Generation,
    digest: StateDigest,
}

#[derive(Debug)]
struct MarkerRecord {
    domain: String,
    integrity_algorithm: String,
}

#[derive(Debug)]
struct DecodedBundle {
    generation: Generation,
    digest: StateDigest,
    domain: String,
    integrity_algorithm: String,
    state: Vec<u8>,
}

impl DecodedBundle {
    fn into_state(mut self) -> Vec<u8> {
        std::mem::take(&mut self.state)
    }
}

impl Drop for DecodedBundle {
    fn drop(&mut self) {
        self.state.fill(0);
    }
}

#[derive(Debug)]
struct AtomicReplaceError {
    source: io::Error,
    published: bool,
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
enum DecodeError {
    Truncated,
    Trailing,
    InvalidMagic,
    InvalidVersion,
    InvalidLength,
    InvalidUtf8,
    InvalidGeneration,
    InvalidDigest,
}

fn validate_root<E>(root: &Path) -> Result<(), FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    if !root.is_absolute() {
        return Err(FileStoreError::RootMustBeAbsolute);
    }
    let mut current = PathBuf::new();
    for component in root.components() {
        current.push(component.as_os_str());
        if current.parent().is_none() {
            continue;
        }
        let metadata = fs::symlink_metadata(&current).map_err(FileStoreError::Io)?;
        if metadata.file_type().is_symlink() || !metadata.is_dir() {
            return Err(FileStoreError::UnsafeRoot);
        }
    }
    Ok(())
}

fn directory_is_empty<E>(root: &Path) -> Result<bool, FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    let mut entries = fs::read_dir(root).map_err(FileStoreError::Io)?;
    match entries.next() {
        None => Ok(true),
        Some(Ok(_)) => Ok(false),
        Some(Err(error)) => Err(FileStoreError::Io(error)),
    }
}

fn reject_unresolved_temporary_artifacts<E>(root: &Path) -> Result<(), FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    for entry in fs::read_dir(root).map_err(FileStoreError::Io)? {
        let entry = entry.map_err(FileStoreError::Io)?;
        let name = entry.file_name();
        if name.to_string_lossy().contains(".tmp-") {
            return Err(FileStoreError::CorruptState);
        }
    }
    Ok(())
}

fn map_marker_read_error<E>(error: FileStoreError<E>) -> FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    match error {
        FileStoreError::Io(io_error) if io_error.kind() == io::ErrorKind::NotFound => {
            FileStoreError::MarkerMissing
        }
        other => other,
    }
}

fn map_current_read_error<E>(error: FileStoreError<E>) -> FileStoreError<E>
where
    E: Error + Send + Sync + 'static,
{
    match error {
        FileStoreError::Io(io_error) if io_error.kind() == io::ErrorKind::NotFound => {
            FileStoreError::CurrentMissing
        }
        other => other,
    }
}

fn read_regular_file<E>(path: &Path, maximum: usize) -> Result<Vec<u8>, FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    let metadata = fs::symlink_metadata(path).map_err(FileStoreError::Io)?;
    if metadata.file_type().is_symlink() || !metadata.is_file() {
        return Err(FileStoreError::UnsafeFileType);
    }
    let maximum_u64 = u64::try_from(maximum).map_err(|_| FileStoreError::CorruptState)?;
    if metadata.len() > maximum_u64 {
        return Err(FileStoreError::CorruptState);
    }
    let file = File::open(path).map_err(FileStoreError::Io)?;
    let take_bound = maximum_u64
        .checked_add(1)
        .ok_or(FileStoreError::CorruptState)?;
    let mut limited = file.take(take_bound);
    let mut bytes = Vec::new();
    limited
        .read_to_end(&mut bytes)
        .map_err(FileStoreError::Io)?;
    if bytes.len() > maximum {
        bytes.fill(0);
        return Err(FileStoreError::CorruptState);
    }
    Ok(bytes)
}

fn write_new_file_and_sync_parent(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let mut file = OpenOptions::new().write(true).create_new(true).open(path)?;
    file.write_all(bytes)?;
    file.flush()?;
    file.sync_all()?;
    let parent = path
        .parent()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "generation has no parent"))?;
    sync_directory(parent)
}

fn atomic_replace(root: &Path, target_name: &str, bytes: &[u8]) -> Result<(), AtomicReplaceError> {
    let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let temporary_name = format!(".{target_name}.tmp-{}-{sequence:016x}", std::process::id());
    let temporary_path = root.join(temporary_name);
    let target_path = root.join(target_name);

    let write_result = (|| -> io::Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary_path)?;
        file.write_all(bytes)?;
        file.flush()?;
        file.sync_all()
    })();
    if let Err(source) = write_result {
        let _ = fs::remove_file(&temporary_path);
        return Err(AtomicReplaceError {
            source,
            published: false,
        });
    }
    if let Err(source) = fs::rename(&temporary_path, &target_path) {
        let _ = fs::remove_file(&temporary_path);
        return Err(AtomicReplaceError {
            source,
            published: false,
        });
    }
    if let Err(source) = sync_directory(root) {
        return Err(AtomicReplaceError {
            source,
            published: true,
        });
    }
    Ok(())
}

fn sync_directory(path: &Path) -> io::Result<()> {
    OpenOptions::new().read(true).open(path)?.sync_all()
}

fn bundle_file_name(generation: Generation) -> String {
    format!("generation-{:020}.hbs", generation.get())
}

fn encode_marker<E>(domain: &str, algorithm: &str) -> Result<Vec<u8>, FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    let domain_len = u16::try_from(domain.len()).map_err(|_| FileStoreError::CorruptState)?;
    let algorithm_len = u16::try_from(algorithm.len()).map_err(|_| FileStoreError::CorruptState)?;
    let mut output = Vec::new();
    output.extend_from_slice(MARKER_MAGIC);
    output.extend_from_slice(&domain_len.to_be_bytes());
    output.extend_from_slice(&algorithm_len.to_be_bytes());
    output.extend_from_slice(domain.as_bytes());
    output.extend_from_slice(algorithm.as_bytes());
    Ok(output)
}

fn decode_marker(bytes: &[u8]) -> Result<MarkerRecord, DecodeError> {
    let mut cursor = SliceCursor::new(bytes);
    if cursor.take(MARKER_MAGIC.len())? != MARKER_MAGIC {
        return Err(DecodeError::InvalidMagic);
    }
    let domain_len = usize::from(cursor.take_u16()?);
    let algorithm_len = usize::from(cursor.take_u16()?);
    if domain_len == 0 || algorithm_len == 0 {
        return Err(DecodeError::InvalidLength);
    }
    let domain = std::str::from_utf8(cursor.take(domain_len)?)
        .map_err(|_| DecodeError::InvalidUtf8)?
        .to_owned();
    let integrity_algorithm = std::str::from_utf8(cursor.take(algorithm_len)?)
        .map_err(|_| DecodeError::InvalidUtf8)?
        .to_owned();
    if !cursor.is_finished() {
        return Err(DecodeError::Trailing);
    }
    Ok(MarkerRecord {
        domain,
        integrity_algorithm,
    })
}

fn encode_current(record: CurrentRecord) -> Vec<u8> {
    let mut output = Vec::new();
    output.extend_from_slice(CURRENT_MAGIC);
    output.extend_from_slice(&record.generation.get().to_be_bytes());
    output.extend_from_slice(&record.digest.bytes());
    output
}

fn decode_current(bytes: &[u8]) -> Result<CurrentRecord, DecodeError> {
    let mut cursor = SliceCursor::new(bytes);
    if cursor.take(CURRENT_MAGIC.len())? != CURRENT_MAGIC {
        return Err(DecodeError::InvalidMagic);
    }
    let generation =
        Generation::new(cursor.take_u64()?).map_err(|_| DecodeError::InvalidGeneration)?;
    let digest_bytes = cursor.take(32)?;
    let mut digest = [0_u8; 32];
    digest.copy_from_slice(digest_bytes);
    let digest = StateDigest::new(digest).map_err(|_| DecodeError::InvalidDigest)?;
    if !cursor.is_finished() {
        return Err(DecodeError::Trailing);
    }
    Ok(CurrentRecord { generation, digest })
}

fn encode_bundle<E>(
    generation: Generation,
    domain: &str,
    algorithm: &str,
    digest: StateDigest,
    state: &[u8],
) -> Result<Vec<u8>, FileStoreError<E>>
where
    E: Error + Send + Sync + 'static,
{
    let domain_len = u16::try_from(domain.len()).map_err(|_| FileStoreError::CorruptState)?;
    let algorithm_len = u16::try_from(algorithm.len()).map_err(|_| FileStoreError::CorruptState)?;
    let state_len = u64::try_from(state.len()).map_err(|_| FileStoreError::CorruptState)?;
    let mut output = Vec::new();
    output.extend_from_slice(BUNDLE_MAGIC);
    output.extend_from_slice(&generation.get().to_be_bytes());
    output.extend_from_slice(&domain_len.to_be_bytes());
    output.extend_from_slice(&algorithm_len.to_be_bytes());
    output.extend_from_slice(&state_len.to_be_bytes());
    output.extend_from_slice(&digest.bytes());
    output.extend_from_slice(domain.as_bytes());
    output.extend_from_slice(algorithm.as_bytes());
    output.extend_from_slice(state);
    Ok(output)
}

fn decode_bundle(bytes: &[u8]) -> Result<DecodedBundle, DecodeError> {
    let mut cursor = SliceCursor::new(bytes);
    if cursor.take(BUNDLE_MAGIC.len())? != BUNDLE_MAGIC {
        return Err(DecodeError::InvalidMagic);
    }
    let generation =
        Generation::new(cursor.take_u64()?).map_err(|_| DecodeError::InvalidGeneration)?;
    let domain_len = usize::from(cursor.take_u16()?);
    let algorithm_len = usize::from(cursor.take_u16()?);
    let state_len = usize::try_from(cursor.take_u64()?).map_err(|_| DecodeError::InvalidLength)?;
    let digest_bytes = cursor.take(32)?;
    let mut digest = [0_u8; 32];
    digest.copy_from_slice(digest_bytes);
    let digest = StateDigest::new(digest).map_err(|_| DecodeError::InvalidDigest)?;
    if domain_len == 0
        || algorithm_len == 0
        || state_len == 0
        || state_len > heptabao_storage_api::MAX_OPAQUE_STATE_BYTES
    {
        return Err(DecodeError::InvalidLength);
    }
    let domain = std::str::from_utf8(cursor.take(domain_len)?)
        .map_err(|_| DecodeError::InvalidUtf8)?
        .to_owned();
    let integrity_algorithm = std::str::from_utf8(cursor.take(algorithm_len)?)
        .map_err(|_| DecodeError::InvalidUtf8)?
        .to_owned();
    let state = cursor.take(state_len)?.to_vec();
    if !cursor.is_finished() {
        return Err(DecodeError::Trailing);
    }
    Ok(DecodedBundle {
        generation,
        digest,
        domain,
        integrity_algorithm,
        state,
    })
}

#[derive(Debug)]
struct SliceCursor<'a> {
    bytes: &'a [u8],
    offset: usize,
}

impl<'a> SliceCursor<'a> {
    const fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, offset: 0 }
    }

    fn take(&mut self, length: usize) -> Result<&'a [u8], DecodeError> {
        let end = self
            .offset
            .checked_add(length)
            .ok_or(DecodeError::InvalidLength)?;
        let value = self
            .bytes
            .get(self.offset..end)
            .ok_or(DecodeError::Truncated)?;
        self.offset = end;
        Ok(value)
    }

    fn take_u16(&mut self) -> Result<u16, DecodeError> {
        let bytes = self.take(2)?;
        Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
    }

    fn take_u64(&mut self) -> Result<u64, DecodeError> {
        let bytes = self.take(8)?;
        Ok(u64::from_be_bytes([
            bytes[0], bytes[1], bytes[2], bytes[3], bytes[4], bytes[5], bytes[6], bytes[7],
        ]))
    }

    fn is_finished(&self) -> bool {
        self.offset == self.bytes.len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use heptabao_storage_api::IntegrityAlgorithmId;
    use std::time::{SystemTime, UNIX_EPOCH};

    #[derive(Clone, Copy, Debug, Eq, PartialEq)]
    enum TestIntegrityError {
        Contract(StorageContractError),
    }

    impl fmt::Display for TestIntegrityError {
        fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
            match self {
                Self::Contract(error) => write!(formatter, "test integrity failure: {error}"),
            }
        }
    }

    impl Error for TestIntegrityError {}

    #[derive(Debug)]
    struct TestIntegrity {
        algorithm: IntegrityAlgorithmId,
    }

    impl TestIntegrity {
        fn new() -> Result<Self, StorageContractError> {
            Ok(Self {
                algorithm: IntegrityAlgorithmId::new("test-digest-v1".to_owned())?,
            })
        }
    }

    impl IntegrityProvider for TestIntegrity {
        type Error = TestIntegrityError;

        fn algorithm_id(&self) -> &IntegrityAlgorithmId {
            &self.algorithm
        }

        fn digest(
            &self,
            domain: &StoreDomain,
            generation: Generation,
            state: &[u8],
        ) -> Result<StateDigest, Self::Error> {
            let mut output = [0_u8; 32];
            for (index, byte) in domain
                .as_str()
                .as_bytes()
                .iter()
                .copied()
                .chain(generation.get().to_be_bytes())
                .chain(state.iter().copied())
                .enumerate()
            {
                let slot = index % output.len();
                output[slot] = output[slot]
                    .wrapping_add(byte)
                    .rotate_left((slot % 7) as u32);
            }
            if output == [0; 32] {
                output[0] = 1;
            }
            StateDigest::new(output).map_err(TestIntegrityError::Contract)
        }
    }

    #[derive(Debug)]
    struct TempDirectory {
        path: PathBuf,
    }

    impl TempDirectory {
        fn new() -> io::Result<Self> {
            let sequence = TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed);
            let nanos = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(io::Error::other)?
                .as_nanos();
            let path = std::env::temp_dir().join(format!(
                "heptabao-single-node-store-{}-{sequence:016x}-{nanos:x}",
                std::process::id()
            ));
            fs::create_dir(&path)?;
            Ok(Self { path })
        }
    }

    impl Drop for TempDirectory {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn domain() -> Result<StoreDomain, StorageContractError> {
        StoreDomain::new("heptabao/test-state".to_owned())
    }

    #[test]
    fn create_commit_load_and_reopen_round_trip() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        assert!(temporary.is_ok());
        assert!(domain.is_ok());
        assert!(integrity.is_ok());
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            let store = FileGenerationStore::create_new(&temporary.path, domain.clone(), integrity);
            assert!(store.is_ok());
            if let Ok(mut store) = store {
                let candidate = OpaqueState::new(b"sealed-generation-one".to_vec());
                assert!(candidate.is_ok());
                if let Ok(candidate) = candidate {
                    let receipt = store.commit(None, candidate);
                    assert!(receipt.is_ok());
                    assert_eq!(store.current_generation(), Some(Generation::INITIAL));
                }
                let loaded = store.load_current();
                assert!(loaded.is_ok());
                if let Ok(Some(loaded)) = loaded {
                    assert_eq!(loaded.state.as_bytes(), b"sealed-generation-one");
                }
            }
            let reopened = TestIntegrity::new().and_then(|integrity| {
                FileGenerationStore::reopen_existing(&temporary.path, domain, integrity).map_err(
                    |error| match error {
                        FileStoreError::Contract(contract) => contract,
                        _ => StorageContractError::InvalidOpaqueState,
                    },
                )
            });
            assert!(reopened.is_ok());
            if let Ok(reopened) = reopened {
                assert_eq!(reopened.current_generation(), Some(Generation::INITIAL));
            }
        }
    }

    #[test]
    fn compare_and_swap_rejects_stale_expected_generation() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            let store = FileGenerationStore::create_new(&temporary.path, domain, integrity);
            assert!(store.is_ok());
            if let Ok(mut store) = store {
                let first = OpaqueState::new(b"first".to_vec());
                assert!(first.is_ok());
                if let Ok(first) = first {
                    assert!(store.commit(None, first).is_ok());
                }
                let stale = OpaqueState::new(b"stale".to_vec());
                assert!(stale.is_ok());
                if let Ok(stale) = stale {
                    assert!(matches!(
                        store.commit(None, stale),
                        Err(FileStoreError::GenerationConflict { .. })
                    ));
                }
            }
        }
    }

    #[test]
    fn corrupt_bundle_is_never_silently_reopened() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            let store = FileGenerationStore::create_new(&temporary.path, domain.clone(), integrity);
            assert!(store.is_ok());
            if let Ok(mut store) = store {
                let candidate = OpaqueState::new(b"state".to_vec());
                assert!(candidate.is_ok());
                if let Ok(candidate) = candidate {
                    assert!(store.commit(None, candidate).is_ok());
                }
            }
            let bundle = temporary.path.join(bundle_file_name(Generation::INITIAL));
            assert!(fs::write(&bundle, b"corrupt").is_ok());
            let reopened = TestIntegrity::new().map(|integrity| {
                FileGenerationStore::reopen_existing(&temporary.path, domain, integrity)
            });
            assert!(matches!(reopened, Ok(Err(FileStoreError::CorruptState))));
        }
    }

    #[test]
    fn missing_current_after_initialization_fails_closed() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            let store = FileGenerationStore::create_new(&temporary.path, domain.clone(), integrity);
            assert!(store.is_ok());
            if let Ok(mut store) = store {
                let candidate = OpaqueState::new(b"state".to_vec());
                if let Ok(candidate) = candidate {
                    assert!(store.commit(None, candidate).is_ok());
                }
            }
            assert!(fs::remove_file(temporary.path.join(CURRENT_NAME)).is_ok());
            let reopened = TestIntegrity::new().map(|integrity| {
                FileGenerationStore::reopen_existing(&temporary.path, domain, integrity)
            });
            assert!(matches!(reopened, Ok(Err(FileStoreError::CurrentMissing))));
        }
    }

    #[test]
    fn legacy_state_requires_explicit_adoption() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            let store = FileGenerationStore::create_new(&temporary.path, domain.clone(), integrity);
            if let Ok(mut store) = store {
                let candidate = OpaqueState::new(b"legacy-state".to_vec());
                if let Ok(candidate) = candidate {
                    assert!(store.commit(None, candidate).is_ok());
                }
            }
            assert!(fs::remove_file(temporary.path.join(MARKER_NAME)).is_ok());
            let reopen_attempt = TestIntegrity::new().map(|integrity| {
                FileGenerationStore::reopen_existing(&temporary.path, domain.clone(), integrity)
            });
            assert!(matches!(
                reopen_attempt,
                Ok(Err(FileStoreError::MarkerMissing))
            ));
            let adopted = TestIntegrity::new().map(|integrity| {
                FileGenerationStore::adopt_legacy(&temporary.path, domain, integrity)
            });
            assert!(matches!(adopted, Ok(Ok(_))));
        }
    }

    #[test]
    fn create_new_rejects_non_empty_root() {
        let temporary = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(temporary), Ok(domain), Ok(integrity)) = (temporary, domain, integrity) {
            assert!(fs::write(temporary.path.join("unexpected"), b"x").is_ok());
            let store = FileGenerationStore::create_new(&temporary.path, domain, integrity);
            assert!(matches!(store, Err(FileStoreError::DirectoryNotEmpty)));
        }
    }

    #[cfg(unix)]
    #[test]
    fn symlinked_storage_root_is_rejected() {
        use std::os::unix::fs::symlink;

        let parent = TempDirectory::new();
        let target = TempDirectory::new();
        let domain = domain();
        let integrity = TestIntegrity::new();
        if let (Ok(parent), Ok(target), Ok(domain), Ok(integrity)) =
            (parent, target, domain, integrity)
        {
            let link = parent.path.join("root-link");
            assert!(symlink(&target.path, &link).is_ok());
            let store = FileGenerationStore::create_new(link, domain, integrity);
            assert!(matches!(store, Err(FileStoreError::UnsafeRoot)));
        }
    }
}
