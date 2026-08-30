#!/usr/bin/env python3
"""Apply the final V1.3.1 repository-controlled gap closure to one exact target tree."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path.cwd()


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def write(relative: str, value: str) -> None:
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def replace_once(relative: str, old: str, new: str) -> None:
    value = read(relative)
    count = value.count(old)
    if count != 1:
        raise SystemExit(
            f"{relative}: expected exactly one replacement, found {count}: {old[:120]!r}"
        )
    write(relative, value.replace(old, new, 1))


def append_once(relative: str, heading: str, section: str) -> None:
    value = read(relative)
    if heading in value:
        raise SystemExit(f"{relative}: section already exists: {heading}")
    write(relative, value.rstrip() + "\n\n" + section.strip() + "\n")


def create_new(relative: str, value: str) -> None:
    path = ROOT / relative
    if path.exists():
        raise SystemExit(f"new file already exists: {relative}")
    write(relative, value)


# ---------------------------------------------------------------------------
# Explicit request-identity and response-delivery audit phases.
# ---------------------------------------------------------------------------
replace_once(
    "crates/heptabao-protocol/src/lib.rs",
    """pub enum AuditPhase {
    RequestAccepted,
    RequestRejected,
    ResponsePrepared,
    ResponseCommitted,
    ResponseAuditFailedAfterCommit,
}
""",
    """pub enum AuditPhase {
    RequestIdentityBound,
    RequestAccepted,
    RequestRejected,
    ResponsePrepared,
    ResponseCommitted,
    ResponseAuditFailedAfterCommit,
    ResponseDelivered,
    ResponseDeliveryFailed,
}
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """impl SharedAuditSink {
    fn new(inner: FileAuditSink) -> Self {
        Self {
            inner: Arc::new(Mutex::new(inner)),
        }
    }
}
""",
    """impl SharedAuditSink {
    fn new(inner: FileAuditSink) -> Self {
        Self {
            inner: Arc::new(Mutex::new(inner)),
        }
    }

    fn record_request_correlation(
        &self,
        transport_attempt_id: &RequestId,
        effective_request_id: &RequestId,
    ) -> Result<(), AuditError> {
        let mut guard = self
            .inner
            .lock()
            .map_err(|_| AuditError::InjectedFailure)?;
        guard.record(&AuditEvent {
            request_id: transport_attempt_id.clone(),
            operation: None,
            phase: AuditPhase::RequestIdentityBound,
            commit: CommitDisposition::NotAttempted,
            status_code: 0,
            detail_code: "request-identity-attempt",
        })?;
        guard.record(&AuditEvent {
            request_id: effective_request_id.clone(),
            operation: None,
            phase: AuditPhase::RequestIdentityBound,
            commit: CommitDisposition::NotAttempted,
            status_code: 0,
            detail_code: "request-identity-effective",
        })
    }
}
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """impl ServeError {
    fn from_protocol(error: ProtocolError) -> Self {
        Self {
            status_code: protocol_status(error),
            detail_code: protocol_detail_code(error),
            message: error.to_string(),
        }
    }
}
""",
    """impl ServeError {
    fn from_protocol(error: ProtocolError) -> Self {
        Self {
            status_code: protocol_status(error),
            detail_code: protocol_detail_code(error),
            message: error.to_string(),
        }
    }

    const fn public_message(&self) -> &'static str {
        match self.status_code {
            400 => "invalid request",
            408 => "request deadline exceeded",
            409 => "request identity conflict",
            413 => "request too large",
            429 => "connection capacity exhausted",
            500 | 503 => "service unavailable",
            _ => "request failed",
        }
    }
}
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """                    let status = if audit_ok { error.status_code } else { 503 };
                    let message = if audit_ok {
                        error.message
                    } else {
                        "transport rejection audit unavailable".to_owned()
                    };
                    let response = error_response(status, &message);
""",
    """                    eprintln!(
                        "transport rejection detail={} diagnostic={}",
                        error.detail_code, error.message
                    );
                    let status = if audit_ok { error.status_code } else { 503 };
                    let message = if audit_ok {
                        error.public_message()
                    } else {
                        "transport rejection audit unavailable"
                    };
                    let response = error_response(status, message);
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """    let request_id = match request.headers.get("x-heptabao-request-id") {
        Some(raw) => request_ids.claim(raw, Instant::now())?,
        None => attempt_id,
    };
    let deadline = received
""",
    """    let request_id = match request.headers.get("x-heptabao-request-id") {
        Some(raw) => request_ids.claim(raw, Instant::now())?,
        None => attempt_id.clone(),
    };
    audit
        .record_request_correlation(&attempt_id, &request_id)
        .map_err(|_| ServeError {
            status_code: 503,
            detail_code: "request-identity-correlation-audit-failed",
            message: "request identity correlation audit failed".to_owned(),
        })?;
    let deadline = received
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """    if let Err(error) = write_response_with_timeout(stream, &response) {
        let _audit_result = record_delivery_failure(audit, request_id, response.committed);
        eprintln!("response delivery failed: {error}");
    }
    Ok(())
""",
    """    match write_response_with_timeout(stream, &response) {
        Ok(()) => {
            if let Err(error) = record_delivery_outcome(
                audit,
                &request_id,
                response.committed,
                response.status_code,
                true,
            ) {
                eprintln!("response delivery success audit failed: {error}");
            }
        }
        Err(error) => {
            let _audit_result = record_delivery_outcome(
                audit,
                &request_id,
                response.committed,
                response.status_code,
                false,
            );
            eprintln!("response delivery failed: {error}");
        }
    }
    Ok(())
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """fn record_delivery_failure(
    audit: &SharedAuditSink,
    request_id: RequestId,
    committed: bool,
) -> Result<(), AuditError> {
    let mut sink = audit.clone();
    sink.record(&AuditEvent {
        request_id,
        operation: None,
        phase: if committed {
            AuditPhase::ResponseCommitted
        } else {
            AuditPhase::ResponsePrepared
        },
        commit: if committed {
            CommitDisposition::Committed
        } else {
            CommitDisposition::NotCommitted
        },
        status_code: 503,
        detail_code: if committed {
            "response-delivery-failed-after-commit"
        } else {
            "response-delivery-failed-before-commit"
        },
    })
}
""",
    """fn record_delivery_outcome(
    audit: &SharedAuditSink,
    request_id: &RequestId,
    committed: bool,
    status_code: u16,
    delivered: bool,
) -> Result<(), AuditError> {
    let mut sink = audit.clone();
    sink.record(&AuditEvent {
        request_id: request_id.clone(),
        operation: None,
        phase: if delivered {
            AuditPhase::ResponseDelivered
        } else {
            AuditPhase::ResponseDeliveryFailed
        },
        commit: if committed {
            CommitDisposition::Committed
        } else {
            CommitDisposition::NotCommitted
        },
        status_code,
        detail_code: match (delivered, committed) {
            (true, true) => "response-delivered-after-commit",
            (true, false) => "response-delivered-before-commit",
            (false, true) => "response-delivery-failed-after-commit",
            (false, false) => "response-delivery-failed-before-commit",
        },
    })
}
""",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    "use super::{render_response, RequestIdRegistry};",
    "use super::{render_response, RequestIdRegistry, ServeError};",
)

replace_once(
    "crates/heptabao-p0-server/src/main.rs",
    """    #[test]
    fn request_id_registry_fails_closed_when_saturated() {
        let registry = RequestIdRegistry::new(1, Duration::from_secs(60));
        let now = Instant::now();
        assert!(registry.claim("client-request-0001", now).is_ok());
        assert!(registry.claim("client-request-0002", now).is_err());
    }
}
""",
    """    #[test]
    fn request_id_registry_fails_closed_when_saturated() {
        let registry = RequestIdRegistry::new(1, Duration::from_secs(60));
        let now = Instant::now();
        assert!(registry.claim("client-request-0001", now).is_ok());
        assert!(registry.claim("client-request-0002", now).is_err());
    }

    #[test]
    fn public_transport_errors_never_expose_internal_diagnostics() {
        let error = ServeError {
            status_code: 503,
            detail_code: "request-read-io-failed",
            message: "/private/path: raw operating-system diagnostic".to_owned(),
        };
        assert_eq!(error.public_message(), "service unavailable");
        assert!(!error.public_message().contains("private"));
        assert!(!error.public_message().contains("operating-system"));
    }
}
""",
)

# ---------------------------------------------------------------------------
# Versioned per-store identity: detect same-path real-directory replacement.
# ---------------------------------------------------------------------------
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    "use std::sync::atomic::{AtomicU64, Ordering};\n",
    "use std::sync::atomic::{AtomicU64, Ordering};\nuse std::time::{SystemTime, UNIX_EPOCH};\n",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    "static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);",
    "static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(1);\nstatic STORE_ID_SEQUENCE: AtomicU64 = AtomicU64::new(1);",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """#[derive(Clone, Debug, Deserialize, Serialize)]
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
        if self.domain != expected_domain {
            return Err(invalid(format!(
                "initialization marker domain mismatch: expected {expected_domain}, got {}",
                self.domain
            )));
        }
        if self.authoritative_file != expected_file {
            return Err(invalid(format!(
                "initialization marker file mismatch: expected {expected_file}, got {}",
                self.authoritative_file
            )));
        }
        Ok(())
    }
}
""",
    """fn new_store_identity() -> io::Result<String> {
    let nanos = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| invalid("system time is before the Unix epoch"))?
        .as_nanos();
    let sequence = STORE_ID_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    Ok(format!(
        "hb-store-v2-{}-{nanos:032x}-{sequence:016x}",
        std::process::id()
    ))
}

fn validate_store_identity(value: &str) -> io::Result<()> {
    if value.len() < 24
        || value.len() > 128
        || !value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
    {
        return Err(invalid("initialization marker store identity is invalid"));
    }
    Ok(())
}

#[derive(Clone, Debug, Deserialize, Serialize)]
struct PersistentInitializationMarker {
    format_version: u16,
    domain: String,
    authoritative_file: String,
    store_identity: String,
}

impl PersistentInitializationMarker {
    fn new(domain: &str, authoritative_file: &str, store_identity: String) -> Self {
        Self {
            format_version: 2,
            domain: domain.to_owned(),
            authoritative_file: authoritative_file.to_owned(),
            store_identity,
        }
    }

    fn validate(&self, expected_domain: &str, expected_file: &str) -> io::Result<()> {
        if self.format_version != 2 {
            return Err(invalid("unsupported initialization marker version"));
        }
        if self.domain != expected_domain {
            return Err(invalid(format!(
                "initialization marker domain mismatch: expected {expected_domain}, got {}",
                self.domain
            )));
        }
        if self.authoritative_file != expected_file {
            return Err(invalid(format!(
                "initialization marker file mismatch: expected {expected_file}, got {}",
                self.authoritative_file
            )));
        }
        validate_store_identity(&self.store_identity)
    }
}
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """fn persist_initialization_marker(
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
""",
    """fn persist_initialization_marker(
    root: &Path,
    domain: &str,
    authoritative_file: &str,
    store_identity: &str,
) -> io::Result<()> {
    validate_store_identity(store_identity)?;
    write_json(
        &initialization_marker_path(root),
        INITIALIZATION_MAGIC,
        &PersistentInitializationMarker::new(
            domain,
            authoritative_file,
            store_identity.to_owned(),
        ),
    )
}

fn verify_active_store_identity(
    data_path: &Path,
    domain: &str,
    authoritative_file: &str,
    expected_identity: &str,
) -> io::Result<()> {
    let root = data_path
        .parent()
        .ok_or_else(|| invalid("durable data path has no parent directory"))?;
    require_real_directory(root, "active durable store root")?;
    let marker = read_initialization_marker(root, domain, authoritative_file)?
        .ok_or_else(|| invalid("active durable store lost its initialization marker"))?;
    if marker.store_identity != expected_identity {
        return Err(invalid("active durable store identity changed"));
    }
    if !regular_file_status(data_path, "active authoritative generation")? {
        return Err(invalid(
            "active durable store lost its authoritative generation",
        ));
    }
    Ok(())
}
""",
)

replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """pub struct DurableLogStore {
    state_path: PathBuf,
    state: Arc<Mutex<PersistentLogState>>,
}
""",
    """pub struct DurableLogStore {
    state_path: PathBuf,
    store_identity: String,
    state: Arc<Mutex<PersistentLogState>>,
}
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let state = PersistentLogState::default();
        write_json(&state_path, LOG_MAGIC, &state)?;
        persist_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
""",
    """        let state = PersistentLogState::default();
        let store_identity = new_store_identity()?;
        write_json(&state_path, LOG_MAGIC, &state)?;
        persist_initialization_marker(
            root,
            LOG_DOMAIN,
            "raft-log.bin",
            &store_identity,
        )?;
        Ok(Self {
            state_path,
            store_identity,
            state: Arc::new(Mutex::new(state)),
        })
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let marker = read_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        if marker.is_none() {
            return Err(invalid(
                "raft log store is not initialized; explicit legacy adoption is required",
            ));
        }
""",
    """        let marker = read_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?
            .ok_or_else(|| {
                invalid(
                    "raft log store is not initialized; explicit legacy adoption is required",
                )
            })?;
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        discard_stale_previous_after_validation(&state_path)?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
""",
    """        discard_stale_previous_after_validation(&state_path)?;
        Ok(Self {
            state_path,
            store_identity: marker.store_identity,
            state: Arc::new(Mutex::new(state)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        discard_stale_previous_after_validation(&state_path)?;
        persist_initialization_marker(root, LOG_DOMAIN, "raft-log.bin")?;
        Ok(Self {
            state_path,
            state: Arc::new(Mutex::new(state)),
        })
    }

    fn persist(&self, state: &PersistentLogState) -> io::Result<()> {
        state.validate()?;
        write_json(&self.state_path, LOG_MAGIC, state)
    }
""",
    """        discard_stale_previous_after_validation(&state_path)?;
        let store_identity = new_store_identity()?;
        persist_initialization_marker(
            root,
            LOG_DOMAIN,
            "raft-log.bin",
            &store_identity,
        )?;
        Ok(Self {
            state_path,
            store_identity,
            state: Arc::new(Mutex::new(state)),
        })
    }

    fn persist(&self, state: &PersistentLogState) -> io::Result<()> {
        state.validate()?;
        verify_active_store_identity(
            &self.state_path,
            LOG_DOMAIN,
            "raft-log.bin",
            &self.store_identity,
        )?;
        write_json(&self.state_path, LOG_MAGIC, state)
    }
""",
)

replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """pub struct DurableStateMachine {
    bundle_path: PathBuf,
    bundle: Arc<Mutex<PersistentStateBundle>>,
}
""",
    """pub struct DurableStateMachine {
    bundle_path: PathBuf,
    store_identity: String,
    bundle: Arc<Mutex<PersistentStateBundle>>,
}
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let bundle = PersistentStateBundle::default();
        write_json(&bundle_path, STATE_BUNDLE_MAGIC, &bundle)?;
        persist_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
""",
    """        let bundle = PersistentStateBundle::default();
        let store_identity = new_store_identity()?;
        write_json(&bundle_path, STATE_BUNDLE_MAGIC, &bundle)?;
        persist_initialization_marker(
            root,
            STATE_MACHINE_DOMAIN,
            "state-bundle.bin",
            &store_identity,
        )?;
        Ok(Self {
            bundle_path,
            store_identity,
            bundle: Arc::new(Mutex::new(bundle)),
        })
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let marker = read_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        if marker.is_none() {
            return Err(invalid(
                "state machine is not initialized; explicit legacy adoption is required",
            ));
        }
""",
    """        let marker = read_initialization_marker(
            root,
            STATE_MACHINE_DOMAIN,
            "state-bundle.bin",
        )?
        .ok_or_else(|| {
            invalid(
                "state machine is not initialized; explicit legacy adoption is required",
            )
        })?;
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        discard_stale_previous_after_validation(&bundle_path)?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
""",
    """        discard_stale_previous_after_validation(&bundle_path)?;
        Ok(Self {
            bundle_path,
            store_identity: marker.store_identity,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    pub fn adopt_legacy(root: impl AsRef<Path>) -> io::Result<Self> {
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        discard_stale_previous_after_validation(&bundle_path)?;
        persist_initialization_marker(root, STATE_MACHINE_DOMAIN, "state-bundle.bin")?;
        Ok(Self {
            bundle_path,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    fn persist_bundle(&self, bundle: &PersistentStateBundle) -> io::Result<()> {
        bundle.validate()?;
        write_json(&self.bundle_path, STATE_BUNDLE_MAGIC, bundle)
    }
""",
    """        discard_stale_previous_after_validation(&bundle_path)?;
        let store_identity = new_store_identity()?;
        persist_initialization_marker(
            root,
            STATE_MACHINE_DOMAIN,
            "state-bundle.bin",
            &store_identity,
        )?;
        Ok(Self {
            bundle_path,
            store_identity,
            bundle: Arc::new(Mutex::new(bundle)),
        })
    }

    fn persist_bundle(&self, bundle: &PersistentStateBundle) -> io::Result<()> {
        bundle.validate()?;
        verify_active_store_identity(
            &self.bundle_path,
            STATE_MACHINE_DOMAIN,
            "state-bundle.bin",
            &self.store_identity,
        )?;
        write_json(&self.bundle_path, STATE_BUNDLE_MAGIC, bundle)
    }
""",
)

replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let mut store = DurableLogStore {
            state_path: blocking_parent.join("raft-log.bin"),
            state: Arc::new(Mutex::new(state)),
        };
""",
    """        let mut store = DurableLogStore {
            state_path: blocking_parent.join("raft-log.bin"),
            store_identity: "hb-store-v2-test-log-identity".to_owned(),
            state: Arc::new(Mutex::new(state)),
        };
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """        let mut state_machine = DurableStateMachine {
            bundle_path: blocking_parent.join("state-bundle.bin"),
            bundle: Arc::new(Mutex::new(initial)),
        };
""",
    """        let mut state_machine = DurableStateMachine {
            bundle_path: blocking_parent.join("state-bundle.bin"),
            store_identity: "hb-store-v2-test-state-identity".to_owned(),
            bundle: Arc::new(Mutex::new(initial)),
        };
""",
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    'PersistentInitializationMarker::new("state-machine", "state-bundle.bin")',
    'PersistentInitializationMarker::new(\n            "state-machine",\n            "state-bundle.bin",\n            "hb-store-v2-test-wrong-marker".to_owned(),\n        )',
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    'PersistentInitializationMarker::new(LOG_DOMAIN, "raft-log.bin")',
    'PersistentInitializationMarker::new(\n            LOG_DOMAIN,\n            "raft-log.bin",\n            "hb-store-v2-test-recovered-marker".to_owned(),\n        )',
)
replace_once(
    "probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs",
    """    #[test]
    fn legacy_log_adoption_rejects_unresolved_data_temporary_file() {
""",
    """    #[tokio::test]
    async fn active_log_persist_rejects_same_path_directory_replacement() {
        let root = root("active-log-replaced-root");
        let displaced = root.with_extension("displaced");
        let mut store = DurableLogStore::create(&root).expect("create log store");
        fs::rename(&root, &displaced).expect("move active log root");
        fs::create_dir_all(&root).expect("replace active log root");

        let error = store
            .save_committed(None)
            .await
            .expect_err("active persistence must reject a replacement directory");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.join("raft-log.bin").exists());
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(displaced);
    }

    #[tokio::test]
    async fn active_state_persist_rejects_same_path_directory_replacement() {
        let root = root("active-state-replaced-root");
        let displaced = root.with_extension("displaced");
        let mut state = DurableStateMachine::create(&root).expect("create state machine");
        fs::rename(&root, &displaced).expect("move active state root");
        fs::create_dir_all(&root).expect("replace active state root");

        let error = state
            .build_snapshot()
            .await
            .expect_err("active persistence must reject a replacement directory");
        assert_eq!(error.kind(), io::ErrorKind::InvalidData);
        assert!(!root.join("state-bundle.bin").exists());
        let _ = fs::remove_dir_all(root);
        let _ = fs::remove_dir_all(displaced);
    }

    #[test]
    fn legacy_log_adoption_rejects_unresolved_data_temporary_file() {
""",
)

# ---------------------------------------------------------------------------
# Machine-readable closure state, blocker register, matrix and regression suite.
# ---------------------------------------------------------------------------
replace_once(
    "planning/HEPTABAO_V1_3_1_GAP_CLOSURE_STATUS.yaml",
    """  authbus_binding_redaction_and_digest_preimage_hygiene: IMPLEMENTED_SOURCE
execution_required:
""",
    """  authbus_binding_redaction_and_digest_preimage_hygiene: IMPLEMENTED_SOURCE
  request_identity_correlation_and_delivery_outcomes: IMPLEMENTED_SOURCE
  kv_list_direct_owned_response_bytes: IMPLEMENTED_SOURCE
  durable_store_identity_replacement_guard: IMPLEMENTED_SOURCE
  transport_public_error_vocabulary: IMPLEMENTED_SOURCE
blocker_extension: planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml
execution_required:
""",
)

create_new(
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
    """schema: heptabao.blocker-register-extension.v1_3_1
plan_id: HEPTABAO-PLAN-2026-08-28
revision: '1.3.1'
status: ACTIVE_FAIL_CLOSED
inherits: planning/HEPTABAO_BLOCKER_REGISTER_V1_3.yaml
added_blockers:
- id: HB-BLK-REPO-018
  class: REPOSITORY_CONTROLLED
  severity: HIGH
  title: transport attempt and effective request identities were not correlated and delivery phases were ambiguous
  owner_role: protocol-audit-security
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - pre-parse transport attempt and effective request IDs are recorded as one ordered pair before dispatch
  - delivery success and failure use distinct phases and preserve original response status and commit disposition
  - exact-head Rust and transport tests pass
  evidence:
  - crates/heptabao-protocol/src/lib.rs
  - crates/heptabao-p0-server/src/main.rs
  closure_receipt_required: true
- id: HB-BLK-REPO-019
  class: REPOSITORY_CONTROLLED
  severity: HIGH
  title: KV LIST constructed unzeroized transient String copies of secret paths
  owner_role: memory-secrecy
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - LIST response encoding writes directly into one owned byte vector
  - no escaped-key String or Vec<String> staging remains
  - exact-head tests and static semantic validation pass
  evidence:
  - crates/heptabao-p0-server/src/lib.rs
  closure_receipt_required: true
- id: HB-BLK-REPO-020
  class: REPOSITORY_CONTROLLED
  severity: CRITICAL
  title: active durable writes could not distinguish a same-path real-directory replacement
  owner_role: storage-integrity
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - every created or adopted store has a versioned unique marker identity
  - every active write verifies current marker identity and authoritative generation
  - same-path directory replacement tests fail closed for log and state-machine stores
  evidence:
  - probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs
  closure_receipt_required: true
- id: HB-BLK-REPO-021
  class: REPOSITORY_CONTROLLED
  severity: HIGH
  title: raw transport and operating-system diagnostics could be reflected to clients
  owner_role: protocol-security
  state: REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED
  closure_criteria:
  - client responses use a stable bounded public error vocabulary
  - raw diagnostics are retained only server-side
  - exact-head tests prove private path and operating-system text are not reflected
  evidence:
  - crates/heptabao-p0-server/src/main.rs
  closure_receipt_required: true
effective_counts:
  repository_controlled: 21
  external_or_repository_setting: 8
  total: 29
external_blockers_must_remain_open:
- HB-BLK-CTRL-001
- HB-BLK-EXT-001
- HB-BLK-EXT-002
- HB-BLK-EXT-003
- HB-BLK-EXT-004
- HB-BLK-EXT-005
- HB-BLK-EXT-006
- HB-BLK-EXT-007
qualification: false
compatibility_claim: false
authority_effect: NONE
""",
)

replace_once(
    "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_3_1.yaml",
    """closure_semantics:
""",
    """- id: HB-STATE-BLOCKER-REGISTER-V1_3_1
  path: planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml
  kind: NORMATIVE
  owner_role: program-qualification
  digest: RESOLVE_FROM_EXACT_SOURCE
  effective_revision: '1.3.1'
  authority_effect: NONE
closure_semantics:
""",
)

replace_once(
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
    """resource_bounds:
""",
    """- id: P0-TRANSPORT-015
  title: transport attempt and effective request identity are correlated before dispatch
  vector: request supplies a distinct accepted X-HeptaBao-Request-Id
  expected: ORDERED_ATTEMPT_EFFECTIVE_ID_AUDIT_PAIR
  expected_phase: RequestIdentityBound
  expected_dispatch_on_correlation_failure: false
- id: P0-TRANSPORT-016
  title: response delivery success and failure use explicit phases
  vector: normal peer and peer closing before response completion
  expected_phases:
  - ResponseDelivered
  - ResponseDeliveryFailed
  expected_status_binding: ORIGINAL_RESPONSE_STATUS
- id: P0-TRANSPORT-017
  title: internal transport diagnostics are not reflected to clients
  vector: injected I/O diagnostic containing a private path and operating-system text
  expected_public_error_vocabulary: BOUNDED_STABLE
  expected_raw_diagnostic_reflection: false
- id: P0-TRANSPORT-018
  title: KV LIST response avoids transient String copies of secret paths
  vector: multiple nested secret keys encoded into a LIST response
  expected: DIRECT_BYTE_VECTOR_ENCODING
  production_qualification_effect: NONE
resource_bounds:
""",
)

replace_once(
    "docs/plan/HEPTABAO_PLAN_V1_3_1_REPOSITORY_GAP_CLOSURE.md",
    """18. P0 single-field JSON rejects raw unescaped quotes, Authbus request-binding/identity `Debug` is redacted, and the canonical request digest preimage and unsigned signature payload are overwritten immediately after their providers return, including provider failure.
""",
    """18. P0 single-field JSON rejects raw unescaped quotes, Authbus request-binding/identity `Debug` is redacted, and the canonical request digest preimage and unsigned signature payload are overwritten immediately after their providers return, including provider failure;
19. request identity correlation records the pre-parse transport attempt and effective request ID as an ordered pair before dispatch, while response delivery uses explicit success/failure audit phases with original status and commit disposition;
20. KV LIST encodes secret path components directly into one owned response byte vector without transient escaped-key `String` or `Vec<String>` staging;
21. every active durable write verifies a versioned per-store marker identity and rejects a same-path real-directory replacement before publishing a new generation;
22. raw socket, filesystem and operating-system diagnostics remain server-side while clients receive only a bounded public error vocabulary.
""",
)

append_once(
    "docs/audit/HEPTABAO_P0_AUDIT_OUTCOME_PROTOCOL_V1.md",
    "## V1.3.1 request identity and delivery closure",
    """## V1.3.1 request identity and delivery closure

Before dispatch, the audit lane records two adjacent `REQUEST_IDENTITY_BOUND` events while holding one audit lock: first the pre-parse transport-attempt ID, then the effective request ID. A failure before the complete pair is persisted blocks dispatch; a partial pair is therefore diagnostic evidence of an aborted request, never authorization to continue.

Successful response write and flush records `RESPONSE_DELIVERED`. A partial write, timeout, reset or flush failure records `RESPONSE_DELIVERY_FAILED`. Both retain the original response status and the known commit disposition; transport failure never rewrites the operation status to 503 in evidence.

Raw I/O, private path and operating-system diagnostics are server-side only. Client-visible transport failures use a bounded public error vocabulary. These development records do not replace the future durable idempotency ledger or cross-node audit ordering proof.
""",
)

append_once(
    "docs/execution/HEPTABAO_P0_DEV_MEMORY_EXECUTION_CONTRACT_V1.md",
    "## V1.3.1 final repository closure",
    """## V1.3.1 final repository closure

The listener records an ordered transport-attempt/effective-request identity pair before handing an envelope to the state machine. Normal and failed response delivery produce explicit phases and retain the original status and commit disposition. Internal transport diagnostics are never reflected to the peer.

KV LIST writes escaped path bytes directly into one owned response byte vector; the controlled response drop overwrites that vector. No intermediate escaped-key `String` or `Vec<String>` staging is permitted.
""",
)

append_once(
    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    "## V1.3.1 final residual closure",
    """## V1.3.1 final residual closure

| Residual threat | Repository control | Remaining external boundary |
|---|---|---|
| Same-path durable store replacement | a versioned per-store marker identity is verified before every active write; log and state-machine replacement tests fail closed | unrestricted storage copy/rollback still requires an external rollback anchor and power-cut qualification |
| Internal transport diagnostic disclosure | clients receive a bounded public error vocabulary; raw diagnostics stay server-side | production log access control and redaction review remain external |
| KV LIST transient path copies | direct byte-vector JSON encoding removes escaped-key `String` and `Vec<String>` staging | allocator, compiler and kernel residue are not qualified |
| Request identity or delivery ambiguity | mandatory ordered attempt/effective-ID audit pair and explicit delivered/delivery-failed phases | durable idempotency and cross-node audit ordering remain future qualified work |
""",
)

append_once(
    "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md",
    "## 10. Active store identity binding",
    """## 10. Active store identity binding

Every newly created or explicitly adopted durable domain publishes a version-2 initialization marker carrying a bounded per-store identity. `open-existing` captures that identity, and every subsequent active write re-reads and verifies the marker plus the authoritative generation before creating a temporary replacement.

Deleting the root, replacing it with a symlink/non-directory, or replacing it at the same pathname with another real directory fails closed. A copied or forged identity by an attacker with unrestricted storage write authority remains outside this repository-only guard and requires an external rollback anchor, authenticated storage inventory and independent power-cut/filesystem evidence. The verification/write interval also remains subject to filesystem race qualification.
""",
)

append_once(
    "docs/auth/HEPTABAO_AUTHBUS_REQUEST_ID_LIFECYCLE_V1.md",
    "## P0 request-ID correlation",
    """## P0 request-ID correlation

P0 allocates a transport-attempt ID before parsing. When a bounded client-proposed request ID is accepted, the audit lane persists the attempt/effective pair before dispatch. This request-ID correlation is an audit relation only; it does not upgrade the process-local P0 registry into the future HA Authbus replay authority.
""",
)

# ---------------------------------------------------------------------------
# Validator and regression updates.
# ---------------------------------------------------------------------------
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "authbus_binding_redaction_and_digest_preimage_hygiene",
    }
""",
    """        "authbus_binding_redaction_and_digest_preimage_hygiene",
        "request_identity_correlation_and_delivery_outcomes",
        "kv_list_direct_owned_response_bytes",
        "durable_store_identity_replacement_guard",
        "transport_public_error_vocabulary",
    }
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    execution = status.get("execution_required")
""",
    """    require(
        status.get("blocker_extension")
        == "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
        "V1.3.1 blocker extension drift",
    )
    blocker_extension = read_yaml(
        root, "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml"
    )
    added_blockers = blocker_extension.get("added_blockers")
    require(
        isinstance(added_blockers, list) and len(added_blockers) == 4,
        "V1.3.1 blocker extension must contain four repository blockers",
    )
    require(
        {entry.get("id") for entry in added_blockers if isinstance(entry, dict)}
        == {
            "HB-BLK-REPO-018",
            "HB-BLK-REPO-019",
            "HB-BLK-REPO-020",
            "HB-BLK-REPO-021",
        },
        "V1.3.1 blocker extension IDs drift",
    )
    require(
        all(
            entry.get("state")
            == "REMEDIATION_IMPLEMENTED_SOURCE_EXACT_HEAD_REQUIRED"
            for entry in added_blockers
        ),
        "V1.3.1 repository blockers cannot be pre-closed",
    )
    require(blocker_extension.get("qualification") is False, "blocker qualification drift")
    require(
        blocker_extension.get("compatibility_claim") is False,
        "blocker compatibility drift",
    )
    require(
        blocker_extension.get("authority_effect") == "NONE",
        "blocker authority drift",
    )

    execution = status.get("execution_required")
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "request_registry_debug_redacts_live_ids",
        ],
""",
    """            "request_registry_debug_redacts_live_ids",
            "fn record_request_correlation(",
            "AuditPhase::RequestIdentityBound",
            "AuditPhase::ResponseDelivered",
            "AuditPhase::ResponseDeliveryFailed",
            "error.public_message()",
            "public_transport_errors_never_expose_internal_diagnostics",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    require(
        "#[derive(Debug)]\\nstruct RequestIdRegistry" not in main_source,
        "request registry must not derive identifier-bearing Debug",
    )
""",
    """    require(
        "#[derive(Debug)]\\nstruct RequestIdRegistry" not in main_source,
        "request registry must not derive identifier-bearing Debug",
    )
    require(
        "let message = if audit_ok {\\n                        error.message" not in main_source,
        "raw transport diagnostics must not be reflected to clients",
    )
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "body_bytes",
        ],
        "protocol secret, target and deadline source",
""",
    """            "body_bytes",
            "RequestIdentityBound",
            "ResponseDelivered",
            "ResponseDeliveryFailed",
        ],
        "protocol secret, target and deadline source",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    require(
        "#[derive(Clone, Debug, Eq, PartialEq)]\\npub struct P0Response" not in p0_lib_source,
""",
    """    require(
        "let escaped = escape_json(key);" not in p0_lib_source,
        "KV LIST must not stage secret path copies in String values",
    )
    require(
        "#[derive(Clone, Debug, Eq, PartialEq)]\\npub struct P0Response" not in p0_lib_source,
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "legacy_state_adoption_rejects_unresolved_data_temporary_file",
        ],
""",
    """            "legacy_state_adoption_rejects_unresolved_data_temporary_file",
            "store_identity",
            "verify_active_store_identity",
            "active_log_persist_rejects_same_path_directory_replacement",
            "active_state_persist_rejects_same_path_directory_replacement",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """    threat_model = read_text(
        root,
        "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    )
""",
    """    threat_model = read_text(
        root,
        "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    )
    storage_contract = read_text(
        root,
        "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md",
    )
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "raw unescaped quotes",
        ],
        "V1.3.1 plan",
""",
    """            "raw unescaped quotes",
            "request identity correlation",
            "same-path real-directory replacement",
            "bounded public error vocabulary",
            "KV LIST",
        ],
        "V1.3.1 plan",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "Blind replay",
        ],
""",
    """            "Blind replay",
            "P0 request-ID correlation",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "operation-body-forbidden",
        ],
        "P0 audit outcome contract",
""",
    """            "operation-body-forbidden",
            "REQUEST_IDENTITY_BOUND",
            "RESPONSE_DELIVERED",
            "original response status",
        ],
        "P0 audit outcome contract",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "unsigned signature payload vectors",
        ],
        "P0 execution contract",
""",
    """            "unsigned signature payload vectors",
            "request identity",
            "bounded public error vocabulary",
            "directly into one owned response byte vector",
        ],
        "P0 execution contract",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "unsigned signature payload",
        ],
        "V1.3 threat model delta",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
    """            "unsigned signature payload",
            "Same-path durable store replacement",
            "Internal transport diagnostic disclosure",
            "KV LIST transient path copies",
            "Request identity or delivery ambiguity",
        ],
        "V1.3 threat model delta",
    )
    require_tokens(
        storage_contract,
        [
            "Active store identity binding",
            "version-2 initialization marker",
            "same pathname with another real directory",
            "external rollback anchor",
        ],
        "durability contract",
    )

    matrix = read_yaml(root, "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml")
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        isinstance(cases, list) and len(cases) == 14,
        "transport matrix must contain 14 cases",
""",
    """        isinstance(cases, list) and len(cases) == 18,
        "transport matrix must contain 18 cases",
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        len(case_ids) == len(set(case_ids)) == 14,
""",
    """        len(case_ids) == len(set(case_ids)) == 18,
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "P0-TRANSPORT-014",
        }.issubset(set(case_ids)),
""",
    """            "P0-TRANSPORT-014",
            "P0-TRANSPORT-015",
            "P0-TRANSPORT-016",
            "P0-TRANSPORT-017",
            "P0-TRANSPORT-018",
        }.issubset(set(case_ids)),
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """            "test_transport_matrix_names_the_residual_closures",
        ],
""",
    """            "test_transport_matrix_names_the_residual_closures",
            "test_request_identity_and_delivery_phases_are_explicit",
            "test_durable_store_identity_guards_same_path_replacement",
            "test_transport_errors_use_public_messages",
        ],
""",
)
replace_once(
    "scripts/validate_plan_v1_3_1.py",
    """        "18 repository remediations and 14 transport cases source-bound; "
""",
    """        "22 repository remediations and 18 transport cases source-bound; "
""",
)

replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    """        self.assertIn("P0-TRANSPORT-014", cases)
""",
    """        self.assertIn("P0-TRANSPORT-014", cases)
        self.assertIn("P0-TRANSPORT-015", cases)
        self.assertIn("P0-TRANSPORT-016", cases)
        self.assertIn("P0-TRANSPORT-017", cases)
        self.assertIn("P0-TRANSPORT-018", cases)
""",
)
replace_once(
    "tests/plan/test_v1_3_1_residual_hardening.py",
    """

if __name__ == "__main__":
""",
    """

    def test_request_identity_and_delivery_phases_are_explicit(self) -> None:
        main = text("crates/heptabao-p0-server/src/main.rs")
        protocol = text("crates/heptabao-protocol/src/lib.rs")
        self.assertIn("record_request_correlation", main)
        self.assertIn("AuditPhase::RequestIdentityBound", main)
        self.assertIn("AuditPhase::ResponseDelivered", main)
        self.assertIn("AuditPhase::ResponseDeliveryFailed", main)
        self.assertIn("RequestIdentityBound", protocol)
        self.assertIn("ResponseDelivered", protocol)
        self.assertIn("ResponseDeliveryFailed", protocol)

    def test_durable_store_identity_guards_same_path_replacement(self) -> None:
        source = text("probes/h02/openraft-tokio/src/bin/durable_store_lab/store.rs")
        self.assertIn("store_identity", source)
        self.assertIn("verify_active_store_identity", source)
        self.assertIn("active_log_persist_rejects_same_path_directory_replacement", source)
        self.assertIn("active_state_persist_rejects_same_path_directory_replacement", source)

    def test_transport_errors_use_public_messages(self) -> None:
        source = text("crates/heptabao-p0-server/src/main.rs")
        self.assertIn("error.public_message()", source)
        self.assertIn("public_transport_errors_never_expose_internal_diagnostics", source)
        self.assertNotIn(
            "let message = if audit_ok {\\n                        error.message",
            source,
        )


if __name__ == "__main__":
""",
)

replace_once(
    "tests/plan/test_plan_v1_3_1.py",
    """    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
""",
    """    "docs/security/HEPTABAO_V1_3_THREAT_MODEL_DELTA.md",
    "docs/storage/HEPTABAO_DURABILITY_AND_CRASH_CONSISTENCY_CONTRACT_V1.md",
    "planning/HEPTABAO_BLOCKER_REGISTER_V1_3_1.yaml",
    "planning/HEPTABAO_P0_TRANSPORT_TEST_MATRIX_V2.yaml",
""",
)

changed = subprocess.check_output(
    ["git", "status", "--porcelain=v1"], text=True
).splitlines()
if not changed:
    raise SystemExit("closure patch produced no changes")
if any(".github/workflows/" in line for line in changed):
    raise SystemExit(f"target closure must not modify workflows: {changed}")

print("V1.3.1 final repository closure patch applied")
