#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};

use heptabao_kms_contracts::sha256;
use heptabao_plugin_contracts::{
    PluginCapability, PluginContractError, PluginDescriptor, PluginDigest,
};

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct PluginLimits {
    pub maximum_request_bytes: usize,
    pub maximum_response_bytes: usize,
    pub timeout_ms: u64,
}

impl PluginLimits {
    pub fn validate(self) -> Result<Self, PluginHostError> {
        if self.maximum_request_bytes == 0
            || self.maximum_response_bytes == 0
            || self.timeout_ms == 0
        {
            return Err(PluginHostError::InvalidLimits);
        }
        Ok(self)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginManifest {
    descriptor: PluginDescriptor,
    sandbox_provider: String,
    limits: PluginLimits,
    environment_allowlist: BTreeSet<String>,
}

impl PluginManifest {
    pub fn new(
        descriptor: PluginDescriptor,
        sandbox_provider: &str,
        limits: PluginLimits,
        environment_allowlist: BTreeSet<String>,
    ) -> Result<Self, PluginHostError> {
        if sandbox_provider.is_empty()
            || sandbox_provider.len() > 128
            || !sandbox_provider
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err(PluginHostError::SandboxUnavailable);
        }
        for name in &environment_allowlist {
            if !valid_environment_name(name) {
                return Err(PluginHostError::InvalidEnvironment);
            }
        }
        Ok(Self {
            descriptor,
            sandbox_provider: sandbox_provider.to_owned(),
            limits: limits.validate()?,
            environment_allowlist,
        })
    }

    pub fn descriptor(&self) -> &PluginDescriptor {
        &self.descriptor
    }

    pub fn sandbox_provider(&self) -> &str {
        &self.sandbox_provider
    }

    pub fn limits(&self) -> PluginLimits {
        self.limits
    }

    pub fn environment_allowlist(&self) -> &BTreeSet<String> {
        &self.environment_allowlist
    }

    pub fn verify_executable(&self, bytes: &[u8]) -> Result<(), PluginHostError> {
        let observed = format!("sha256:{}", sha256(bytes).to_hex());
        if self.descriptor.digest().as_str() != observed {
            return Err(PluginHostError::ExecutableDigestMismatch);
        }
        Ok(())
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PluginProcessFailure {
    BeforeEntry,
    OutcomeUnknownAfterEntry,
}

pub trait PluginProcess {
    fn invoke(
        &mut self,
        request: &[u8],
        timeout_ms: u64,
        environment: &BTreeMap<String, String>,
    ) -> Result<Vec<u8>, PluginProcessFailure>;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PluginHostState {
    Active,
    ReconciliationRequired,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PluginHostError {
    Contract(PluginContractError),
    InvalidLimits,
    InvalidEnvironment,
    SandboxUnavailable,
    ExecutableDigestMismatch,
    CapabilityDenied,
    RequestTooLarge,
    ResponseTooLarge,
    EnvironmentDenied,
    ProcessBeforeEntry,
    ProcessOutcomeUnknown,
    ReconciliationRequired,
}

impl From<PluginContractError> for PluginHostError {
    fn from(value: PluginContractError) -> Self {
        Self::Contract(value)
    }
}

pub struct PluginHost<P: PluginProcess> {
    manifest: PluginManifest,
    process: P,
    state: PluginHostState,
}

impl<P: PluginProcess> PluginHost<P> {
    pub fn admit(
        manifest: PluginManifest,
        executable_bytes: &[u8],
        process: P,
    ) -> Result<Self, PluginHostError> {
        manifest.verify_executable(executable_bytes)?;
        Ok(Self {
            manifest,
            process,
            state: PluginHostState::Active,
        })
    }

    pub fn state(&self) -> PluginHostState {
        self.state
    }

    pub fn invoke(
        &mut self,
        required_capability: PluginCapability,
        request: &[u8],
        environment: &BTreeMap<String, String>,
    ) -> Result<Vec<u8>, PluginHostError> {
        if self.state == PluginHostState::ReconciliationRequired {
            return Err(PluginHostError::ReconciliationRequired);
        }
        if !self
            .manifest
            .descriptor()
            .capabilities()
            .contains(&required_capability)
        {
            return Err(PluginHostError::CapabilityDenied);
        }
        let limits = self.manifest.limits();
        if request.len() > limits.maximum_request_bytes {
            return Err(PluginHostError::RequestTooLarge);
        }
        if environment
            .keys()
            .any(|name| !self.manifest.environment_allowlist().contains(name))
        {
            return Err(PluginHostError::EnvironmentDenied);
        }
        let response = match self.process.invoke(request, limits.timeout_ms, environment) {
            Ok(response) => response,
            Err(PluginProcessFailure::BeforeEntry) => {
                return Err(PluginHostError::ProcessBeforeEntry);
            }
            Err(PluginProcessFailure::OutcomeUnknownAfterEntry) => {
                self.state = PluginHostState::ReconciliationRequired;
                return Err(PluginHostError::ProcessOutcomeUnknown);
            }
        };
        if response.len() > limits.maximum_response_bytes {
            self.state = PluginHostState::ReconciliationRequired;
            return Err(PluginHostError::ResponseTooLarge);
        }
        Ok(response)
    }

    pub fn reconcile(&mut self, executable_bytes: &[u8]) -> Result<(), PluginHostError> {
        self.manifest.verify_executable(executable_bytes)?;
        self.state = PluginHostState::Active;
        Ok(())
    }
}

fn valid_environment_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_uppercase() || byte.is_ascii_digit() || byte == b'_')
}

#[cfg(test)]
mod tests {
    use super::*;
    use heptabao_plugin_contracts::{PluginId, PluginCapability};

    #[derive(Clone, Copy)]
    enum Behavior {
        Echo,
        BeforeEntry,
        OutcomeUnknown,
    }

    struct FakeProcess {
        behavior: Behavior,
    }

    impl PluginProcess for FakeProcess {
        fn invoke(
            &mut self,
            request: &[u8],
            _timeout_ms: u64,
            _environment: &BTreeMap<String, String>,
        ) -> Result<Vec<u8>, PluginProcessFailure> {
            match self.behavior {
                Behavior::Echo => Ok(request.to_vec()),
                Behavior::BeforeEntry => Err(PluginProcessFailure::BeforeEntry),
                Behavior::OutcomeUnknown => Err(PluginProcessFailure::OutcomeUnknownAfterEntry),
            }
        }
    }

    fn manifest(bytes: &[u8]) -> Option<PluginManifest> {
        let id = PluginId::parse("kv.plugin").ok()?;
        let digest = PluginDigest::parse(&format!("sha256:{}", sha256(bytes).to_hex())).ok()?;
        let descriptor = PluginDescriptor::new(
            id,
            digest,
            1,
            BTreeSet::from([PluginCapability::ReadRequest]),
        )
        .ok()?;
        PluginManifest::new(
            descriptor,
            "sandbox-v1",
            PluginLimits {
                maximum_request_bytes: 16,
                maximum_response_bytes: 16,
                timeout_ms: 100,
            },
            BTreeSet::from(["REQUEST_ID".to_owned()]),
        )
        .ok()
    }

    #[test]
    fn digest_capability_and_environment_are_exact() {
        let executable = b"plugin-binary";
        let Some(manifest) = manifest(executable) else {
            assert!(false);
            return;
        };
        let Ok(mut host) = PluginHost::admit(
            manifest,
            executable,
            FakeProcess {
                behavior: Behavior::Echo,
            },
        ) else {
            assert!(false);
            return;
        };
        assert_eq!(
            host.invoke(
                PluginCapability::ReadRequest,
                b"request",
                &BTreeMap::from([("REQUEST_ID".to_owned(), "r-1".to_owned())]),
            ),
            Ok(b"request".to_vec())
        );
        assert_eq!(
            host.invoke(
                PluginCapability::ExternalNetwork,
                b"request",
                &BTreeMap::new(),
            ),
            Err(PluginHostError::CapabilityDenied)
        );
        assert_eq!(
            host.invoke(
                PluginCapability::ReadRequest,
                b"request",
                &BTreeMap::from([("SECRET".to_owned(), "value".to_owned())]),
            ),
            Err(PluginHostError::EnvironmentDenied)
        );
    }

    #[test]
    fn outcome_unknown_fences_subsequent_invocation_until_reconciliation() {
        let executable = b"plugin-binary";
        let Some(manifest) = manifest(executable) else {
            assert!(false);
            return;
        };
        let Ok(mut host) = PluginHost::admit(
            manifest,
            executable,
            FakeProcess {
                behavior: Behavior::OutcomeUnknown,
            },
        ) else {
            assert!(false);
            return;
        };
        assert_eq!(
            host.invoke(
                PluginCapability::ReadRequest,
                b"request",
                &BTreeMap::new(),
            ),
            Err(PluginHostError::ProcessOutcomeUnknown)
        );
        assert_eq!(
            host.invoke(
                PluginCapability::ReadRequest,
                b"request",
                &BTreeMap::new(),
            ),
            Err(PluginHostError::ReconciliationRequired)
        );
        assert_eq!(host.reconcile(executable), Ok(()));
    }

    #[test]
    fn before_entry_failure_does_not_poison_the_host() {
        let executable = b"plugin-binary";
        let Some(manifest) = manifest(executable) else {
            assert!(false);
            return;
        };
        let Ok(mut host) = PluginHost::admit(
            manifest,
            executable,
            FakeProcess {
                behavior: Behavior::BeforeEntry,
            },
        ) else {
            assert!(false);
            return;
        };
        assert_eq!(
            host.invoke(
                PluginCapability::ReadRequest,
                b"request",
                &BTreeMap::new(),
            ),
            Err(PluginHostError::ProcessBeforeEntry)
        );
        assert_eq!(host.state(), PluginHostState::Active);
    }
}
