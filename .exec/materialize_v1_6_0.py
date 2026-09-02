#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import textwrap
import tomllib
from pathlib import Path
from typing import Any

import yaml

PLAN_ID = "HEPTABAO-PLAN-2026-09-02-V1.6.0"
NEW_CRATES = [
    "heptabao-kms-contracts",
    "heptabao-runtime",
    "heptabao-recovery-providers",
    "heptabao-lifecycle-ops",
]
BASELINE_CRATES = {
    "heptabao-authbus-contracts", "heptabao-barrier-api", "heptabao-durable-core",
    "heptabao-filesystem-guard", "heptabao-governance", "heptabao-journal-api",
    "heptabao-journaled-core", "heptabao-key-lifecycle", "heptabao-operation-ledger",
    "heptabao-oracle-observer", "heptabao-p0-server", "heptabao-platform-bakeoff",
    "heptabao-platform-contracts", "heptabao-protocol", "heptabao-recovery-core",
    "heptabao-rollback-anchor", "heptabao-single-node-journal", "heptabao-single-node-store",
    "heptabao-storage-api", "heptabao-namespace", "heptabao-policy", "heptabao-identity",
    "heptabao-token", "heptabao-lease", "heptabao-system", "heptabao-plugin-contracts",
    "heptabao-kv", "heptabao-control-plane",
}
CLAIMS = {
    "qualification": False,
    "compatibility_claim": False,
    "selected_candidates": [],
    "selection_effect": "NONE",
    "production_authority": False,
    "migration_authority": False,
    "release_authority": False,
    "authority_effect": "NONE",
}


def sh(root: Path, *args: str) -> str:
    return subprocess.check_output(args, cwd=root, text=True).strip()


def file_sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root: Path, relative: str, content: str) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def crate_toml(name: str, dependencies: dict[str, str] | None = None) -> str:
    lines = [
        "[package]", f'name = "{name}"', 'version = "0.1.0"', 'edition = "2024"',
        'rust-version = "1.98"', "publish = false", "", "[lints]", "workspace = true",
    ]
    if dependencies:
        lines.extend(["", "[dependencies]"])
        for dependency, path in sorted(dependencies.items()):
            lines.append(f'{dependency} = {{ path = "{path}" }}')
    return "\n".join(lines) + "\n"


def update_workspace(root: Path) -> None:
    path = root / "Cargo.toml"
    text = path.read_text(encoding="utf-8")
    match = re.search(r"(?ms)(members\s*=\s*\[)(.*?)(\n\s*\])", text)
    if not match:
        raise SystemExit("workspace members block not found")
    body = match.group(2)
    existing = set(re.findall(r'"([^"]+)"', body))
    additions = [f"crates/{name}" for name in NEW_CRATES if f"crates/{name}" not in existing]
    if additions:
        if not body.endswith("\n"):
            body += "\n"
        body += "".join(f'  "{item}",\n' for item in additions)
        path.write_text(text[:match.start(2)] + body + text[match.end(2):], encoding="utf-8")


def kms_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::fmt::{self, Write as _};

#[derive(Clone, Copy, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct Digest32([u8; 32]);

impl Digest32 {
    pub fn from_bytes(value: [u8; 32]) -> Self { Self(value) }
    pub fn as_bytes(&self) -> &[u8; 32] { &self.0 }
    pub fn to_hex(self) -> String {
        let mut output = String::with_capacity(64);
        for byte in self.0 { let _ = write!(&mut output, "{byte:02x}"); }
        output
    }
    pub fn parse_hex(value: &str) -> Result<Self, KmsContractError> {
        if value.len() != 64 || !value.bytes().all(|byte| byte.is_ascii_digit() || matches!(byte, b'a'..=b'f')) {
            return Err(KmsContractError::InvalidDigest);
        }
        let mut output = [0_u8; 32];
        for (index, item) in output.iter_mut().enumerate() {
            *item = u8::from_str_radix(&value[index * 2..index * 2 + 2], 16).map_err(|_| KmsContractError::InvalidDigest)?;
        }
        Ok(Self(output))
    }
}

impl fmt::Debug for Digest32 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.write_str(&self.to_hex()) }
}
impl fmt::Display for Digest32 {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.write_str(&self.to_hex()) }
}

pub fn sha256(input: &[u8]) -> Digest32 {
    const K: [u32; 64] = [
        0x428a2f98,0x71374491,0xb5c0fbcf,0xe9b5dba5,0x3956c25b,0x59f111f1,0x923f82a4,0xab1c5ed5,
        0xd807aa98,0x12835b01,0x243185be,0x550c7dc3,0x72be5d74,0x80deb1fe,0x9bdc06a7,0xc19bf174,
        0xe49b69c1,0xefbe4786,0x0fc19dc6,0x240ca1cc,0x2de92c6f,0x4a7484aa,0x5cb0a9dc,0x76f988da,
        0x983e5152,0xa831c66d,0xb00327c8,0xbf597fc7,0xc6e00bf3,0xd5a79147,0x06ca6351,0x14292967,
        0x27b70a85,0x2e1b2138,0x4d2c6dfc,0x53380d13,0x650a7354,0x766a0abb,0x81c2c92e,0x92722c85,
        0xa2bfe8a1,0xa81a664b,0xc24b8b70,0xc76c51a3,0xd192e819,0xd6990624,0xf40e3585,0x106aa070,
        0x19a4c116,0x1e376c08,0x2748774c,0x34b0bcb5,0x391c0cb3,0x4ed8aa4a,0x5b9cca4f,0x682e6ff3,
        0x748f82ee,0x78a5636f,0x84c87814,0x8cc70208,0x90befffa,0xa4506ceb,0xbef9a3f7,0xc67178f2,
    ];
    let mut message = input.to_vec();
    let bit_len = (message.len() as u64).wrapping_mul(8);
    message.push(0x80);
    while message.len() % 64 != 56 { message.push(0); }
    message.extend_from_slice(&bit_len.to_be_bytes());
    let mut state = [0x6a09e667_u32,0xbb67ae85,0x3c6ef372,0xa54ff53a,0x510e527f,0x9b05688c,0x1f83d9ab,0x5be0cd19];
    for chunk in message.chunks_exact(64) {
        let mut schedule = [0_u32; 64];
        for index in 0..16 {
            schedule[index] = u32::from_be_bytes([chunk[index*4],chunk[index*4+1],chunk[index*4+2],chunk[index*4+3]]);
        }
        for index in 16..64 {
            let s0 = schedule[index-15].rotate_right(7) ^ schedule[index-15].rotate_right(18) ^ (schedule[index-15] >> 3);
            let s1 = schedule[index-2].rotate_right(17) ^ schedule[index-2].rotate_right(19) ^ (schedule[index-2] >> 10);
            schedule[index] = schedule[index-16].wrapping_add(s0).wrapping_add(schedule[index-7]).wrapping_add(s1);
        }
        let [mut a,mut b,mut c,mut d,mut e,mut f,mut g,mut h] = state;
        for index in 0..64 {
            let s1 = e.rotate_right(6) ^ e.rotate_right(11) ^ e.rotate_right(25);
            let choice = (e & f) ^ ((!e) & g);
            let temp1 = h.wrapping_add(s1).wrapping_add(choice).wrapping_add(K[index]).wrapping_add(schedule[index]);
            let s0 = a.rotate_right(2) ^ a.rotate_right(13) ^ a.rotate_right(22);
            let majority = (a & b) ^ (a & c) ^ (b & c);
            let temp2 = s0.wrapping_add(majority);
            h=g; g=f; f=e; e=d.wrapping_add(temp1); d=c; c=b; b=a; a=temp1.wrapping_add(temp2);
        }
        state[0]=state[0].wrapping_add(a); state[1]=state[1].wrapping_add(b); state[2]=state[2].wrapping_add(c); state[3]=state[3].wrapping_add(d);
        state[4]=state[4].wrapping_add(e); state[5]=state[5].wrapping_add(f); state[6]=state[6].wrapping_add(g); state[7]=state[7].wrapping_add(h);
    }
    let mut output = [0_u8; 32];
    for (index, value) in state.into_iter().enumerate() { output[index*4..index*4+4].copy_from_slice(&value.to_be_bytes()); }
    Digest32(output)
}

#[derive(Clone, Eq, PartialEq)]
pub struct SecretMaterial(Vec<u8>);
impl SecretMaterial {
    pub fn new(value: Vec<u8>) -> Result<Self, KmsContractError> { if value.is_empty() { Err(KmsContractError::EmptySecret) } else { Ok(Self(value)) } }
    pub fn expose(&self) -> &[u8] { &self.0 }
    pub fn len(&self) -> usize { self.0.len() }
    pub fn is_empty(&self) -> bool { self.0.is_empty() }
    pub fn into_bytes(mut self) -> Vec<u8> { std::mem::take(&mut self.0) }
}
impl fmt::Debug for SecretMaterial {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.debug_struct("SecretMaterial").field("len", &self.0.len()).finish_non_exhaustive() }
}
impl Drop for SecretMaterial { fn drop(&mut self) { self.0.fill(0); } }

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct KeyHandle(String);
impl KeyHandle {
    pub fn parse(value: &str) -> Result<Self, KmsContractError> {
        if value.len() < 8 || value.len() > 192 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte,b'-'|b'_'|b'.'|b':'|b'/')) { return Err(KmsContractError::InvalidHandle); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum KeyPurpose { BarrierWrap, ReceiptSigning, AuditAuthentication, TokenAuthentication }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum KeyState { Active, DecryptOnly, Revoked }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct KeyMetadata { pub handle: KeyHandle, pub purpose: KeyPurpose, pub algorithm: String, pub version: u64, pub state: KeyState }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct WrappedMaterial { pub key: KeyHandle, pub key_version: u64, pub aad_digest: Digest32, pub ciphertext: SecretMaterial }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Signature { pub key: KeyHandle, pub key_version: u64, pub algorithm: String, pub bytes: Vec<u8> }

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum KmsContractError { EmptySecret, InvalidHandle, InvalidDigest, InvalidAlgorithm, InvalidVersion, WrongPurpose, Revoked, VerificationFailed }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum KmsFailure<E> { Contract(KmsContractError), ProviderBeforeEntry(E), OutcomeUnknownAfterEntry(E) }

pub trait KmsProvider {
    type ProviderError;
    fn generate(&mut self, purpose: KeyPurpose, algorithm: &str) -> Result<KeyMetadata, KmsFailure<Self::ProviderError>>;
    fn metadata(&self, handle: &KeyHandle) -> Result<KeyMetadata, KmsFailure<Self::ProviderError>>;
    fn wrap(&mut self, handle: &KeyHandle, plaintext: SecretMaterial, aad: &[u8]) -> Result<WrappedMaterial, KmsFailure<Self::ProviderError>>;
    fn unwrap(&mut self, wrapped: &WrappedMaterial, aad: &[u8]) -> Result<SecretMaterial, KmsFailure<Self::ProviderError>>;
    fn sign(&mut self, handle: &KeyHandle, message: &[u8]) -> Result<Signature, KmsFailure<Self::ProviderError>>;
    fn verify(&self, signature: &Signature, message: &[u8]) -> Result<(), KmsFailure<Self::ProviderError>>;
    fn rotate(&mut self, handle: &KeyHandle) -> Result<KeyMetadata, KmsFailure<Self::ProviderError>>;
    fn revoke(&mut self, handle: &KeyHandle) -> Result<KeyMetadata, KmsFailure<Self::ProviderError>>;
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn sha256_matches_known_vector_and_hex_is_strict() {
        let value = sha256(b"abc");
        assert_eq!(value.to_hex(), "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad");
        assert_eq!(Digest32::parse_hex(&value.to_hex()), Ok(value));
        assert_eq!(Digest32::parse_hex(&value.to_hex().to_uppercase()), Err(KmsContractError::InvalidDigest));
    }
    #[test]
    fn secret_debug_never_exposes_bytes() {
        let Ok(secret) = SecretMaterial::new(b"super-secret-value".to_vec()) else { assert!(false); return; };
        let rendered = format!("{secret:?}");
        assert!(!rendered.contains("super-secret-value")); assert!(rendered.contains("len"));
    }
}
'''


def runtime_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use heptabao_control_plane::{AuditSink, ControlPlane, ControlPlaneError, Request, RequestId, Response};
use heptabao_kms_contracts::SecretMaterial;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuntimeState { Bootstrap, Sealed, Unsealing, Ready, Draining, RecoveryRequired, Stopped }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct SealCapability { generation: u64 }
impl SealCapability { pub fn new(generation: u64) -> Result<Self, RuntimeContractError> { if generation == 0 { Err(RuntimeContractError::InvalidSealGeneration) } else { Ok(Self { generation }) } } pub fn generation(&self) -> u64 { self.generation } }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum SealFailure<E> { BeforeEntry(E), OutcomeUnknownAfterEntry(E) }
pub trait SealProvider {
    type Error;
    fn initialize(&mut self) -> Result<(), SealFailure<Self::Error>>;
    fn unseal(&mut self, material: SecretMaterial) -> Result<SealCapability, SealFailure<Self::Error>>;
    fn seal(&mut self, capability: SealCapability) -> Result<(), SealFailure<Self::Error>>;
}
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RuntimeContractError { InvalidTransition, InvalidSealGeneration }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum RuntimeError<E> { Contract(RuntimeContractError), Sealed, Draining, RecoveryRequired, SealBeforeEntry(E), SealOutcomeUnknown(E), Control(ControlPlaneError) }

pub struct Runtime<S: SealProvider, A: AuditSink> {
    state: RuntimeState,
    seal_provider: S,
    seal_capability: Option<SealCapability>,
    control_plane: ControlPlane<A>,
}

impl<S: SealProvider, A: AuditSink> Runtime<S, A> {
    pub fn new(seal_provider: S, control_plane: ControlPlane<A>) -> Self { Self { state: RuntimeState::Bootstrap, seal_provider, seal_capability: None, control_plane } }
    pub fn state(&self) -> RuntimeState { self.state }
    pub fn initialize(&mut self) -> Result<(), RuntimeError<S::Error>> {
        if self.state != RuntimeState::Bootstrap { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        match self.seal_provider.initialize() {
            Ok(()) => { self.state = RuntimeState::Sealed; Ok(()) }
            Err(SealFailure::BeforeEntry(error)) => Err(RuntimeError::SealBeforeEntry(error)),
            Err(SealFailure::OutcomeUnknownAfterEntry(error)) => { self.state = RuntimeState::RecoveryRequired; Err(RuntimeError::SealOutcomeUnknown(error)) }
        }
    }
    pub fn unseal(&mut self, material: SecretMaterial) -> Result<(), RuntimeError<S::Error>> {
        if self.state != RuntimeState::Sealed { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        self.state = RuntimeState::Unsealing;
        match self.seal_provider.unseal(material) {
            Ok(capability) => { self.seal_capability = Some(capability); self.state = RuntimeState::Ready; Ok(()) }
            Err(SealFailure::BeforeEntry(error)) => { self.state = RuntimeState::Sealed; Err(RuntimeError::SealBeforeEntry(error)) }
            Err(SealFailure::OutcomeUnknownAfterEntry(error)) => { self.state = RuntimeState::RecoveryRequired; Err(RuntimeError::SealOutcomeUnknown(error)) }
        }
    }
    pub fn execute(&mut self, request: Request) -> Result<Response, RuntimeError<S::Error>> {
        match self.state {
            RuntimeState::Ready => {}
            RuntimeState::Sealed | RuntimeState::Bootstrap | RuntimeState::Unsealing => return Err(RuntimeError::Sealed),
            RuntimeState::Draining => return Err(RuntimeError::Draining),
            RuntimeState::RecoveryRequired => return Err(RuntimeError::RecoveryRequired),
            RuntimeState::Stopped => return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)),
        }
        let result = self.control_plane.execute(request);
        if matches!(result, Err(ControlPlaneError::AuditOutcomeUnknown | ControlPlaneError::OutcomeUnknown)) { self.state = RuntimeState::RecoveryRequired; }
        result.map_err(RuntimeError::Control)
    }
    pub fn reconcile_request(&mut self, request_id: &RequestId) -> Result<Response, RuntimeError<S::Error>> {
        if self.state != RuntimeState::RecoveryRequired { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        let result = self.control_plane.confirm_outcome(request_id).map_err(RuntimeError::Control)?;
        self.state = RuntimeState::Ready; Ok(result)
    }
    pub fn begin_drain(&mut self) -> Result<(), RuntimeError<S::Error>> {
        if self.state != RuntimeState::Ready { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        self.state = RuntimeState::Draining; Ok(())
    }
    pub fn resume(&mut self) -> Result<(), RuntimeError<S::Error>> {
        if self.state != RuntimeState::Draining { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        self.state = RuntimeState::Ready; Ok(())
    }
    pub fn seal(&mut self) -> Result<(), RuntimeError<S::Error>> {
        if !matches!(self.state, RuntimeState::Ready | RuntimeState::Draining) { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        let capability = self.seal_capability.take().ok_or(RuntimeError::Contract(RuntimeContractError::InvalidTransition))?;
        match self.seal_provider.seal(capability.clone()) {
            Ok(()) => { self.state = RuntimeState::Sealed; Ok(()) }
            Err(SealFailure::BeforeEntry(error)) => { self.seal_capability = Some(capability); self.state = RuntimeState::Ready; Err(RuntimeError::SealBeforeEntry(error)) }
            Err(SealFailure::OutcomeUnknownAfterEntry(error)) => { self.state = RuntimeState::RecoveryRequired; Err(RuntimeError::SealOutcomeUnknown(error)) }
        }
    }
    pub fn stop(&mut self) -> Result<(), RuntimeError<S::Error>> {
        if self.state != RuntimeState::Sealed { return Err(RuntimeError::Contract(RuntimeContractError::InvalidTransition)); }
        self.state = RuntimeState::Stopped; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;
    use super::*;
    use heptabao_control_plane::{MemoryAuditSink, Operation};
    use heptabao_identity::{EntityId, IdentityStore};
    use heptabao_kv::{KvStore, SecretBytes};
    use heptabao_namespace::{NamespaceId, NamespaceRegistry};
    use heptabao_policy::{Capability, Policy, PolicyRule, PolicyStore, RuleEffect};
    use heptabao_system::{MountEntry, MountId, MountKind, MountTable};
    use heptabao_token::{TokenId, TokenIssue, TokenStore};

    #[derive(Clone, Debug, Eq, PartialEq)] struct TestSealError;
    #[derive(Default)] struct TestSealProvider;
    impl SealProvider for TestSealProvider {
        type Error = TestSealError;
        fn initialize(&mut self) -> Result<(), SealFailure<Self::Error>> { Ok(()) }
        fn unseal(&mut self, material: SecretMaterial) -> Result<SealCapability, SealFailure<Self::Error>> { if material.expose() == b"valid" { SealCapability::new(1).map_err(|_| SealFailure::BeforeEntry(TestSealError)) } else { Err(SealFailure::BeforeEntry(TestSealError)) } }
        fn seal(&mut self, _capability: SealCapability) -> Result<(), SealFailure<Self::Error>> { Ok(()) }
    }

    fn plane(fail_outcome: bool) -> Option<(ControlPlane<MemoryAuditSink>, TokenId)> {
        let entity = EntityId::parse("runtime-entity").ok()?;
        let mut identities = IdentityStore::default(); identities.create_entity(entity.clone(), BTreeSet::new()).ok()?;
        let mut capabilities = BTreeSet::new(); capabilities.extend([Capability::Create, Capability::Read, Capability::Update]);
        let rule = PolicyRule::new(None, "/secret", true, capabilities, RuleEffect::Allow).ok()?;
        let mut policies = PolicyStore::default(); policies.insert(Policy::new("runtime", vec![rule]).ok()?).ok()?;
        let token = TokenId::parse("runtime-token-0001").ok()?;
        let mut tokens = TokenStore::default(); tokens.issue(TokenIssue { id: token.clone(), namespace: NamespaceId::root(), entity, policy_names: BTreeSet::from(["runtime".to_owned()]), issued_at_ms: 0, ttl_ms: 10_000, use_limit: Some(10) }).ok()?;
        let mount_id = MountId::parse("runtime-kv").ok()?; let mount = MountEntry::new(mount_id, NamespaceId::root(), "/secret", MountKind::Kv).ok()?;
        let mut mounts = MountTable::default(); mounts.mount(mount).ok()?;
        let mut audit = MemoryAuditSink::default(); if fail_outcome { audit.fail_next_outcome(); }
        Some((ControlPlane::new(NamespaceRegistry::default(), identities, policies, tokens, mounts, KvStore::new(10).ok()?, audit), token))
    }

    #[test]
    fn sealed_ready_drain_and_stop_transitions_are_enforced() {
        let Some((plane, token)) = plane(false) else { assert!(false); return; };
        let mut runtime = Runtime::new(TestSealProvider, plane);
        assert_eq!(runtime.initialize(), Ok(()));
        let Ok(request_id) = RequestId::parse("runtime-request-0001") else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"value".to_vec()) else { assert!(false); return; };
        let request = Request { id: request_id, namespace: NamespaceId::root(), token, now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value, cas: Some(0) } };
        assert_eq!(runtime.execute(request.clone()), Err(RuntimeError::Sealed));
        let Ok(material) = SecretMaterial::new(b"valid".to_vec()) else { assert!(false); return; };
        assert_eq!(runtime.unseal(material), Ok(())); assert!(runtime.execute(request).is_ok());
        assert_eq!(runtime.begin_drain(), Ok(())); assert_eq!(runtime.state(), RuntimeState::Draining);
        assert_eq!(runtime.seal(), Ok(())); assert_eq!(runtime.stop(), Ok(())); assert_eq!(runtime.state(), RuntimeState::Stopped);
    }

    #[test]
    fn possible_effect_moves_runtime_to_recovery_required() {
        let Some((plane, token)) = plane(true) else { assert!(false); return; };
        let mut runtime = Runtime::new(TestSealProvider, plane); assert_eq!(runtime.initialize(), Ok(()));
        let Ok(material) = SecretMaterial::new(b"valid".to_vec()) else { assert!(false); return; }; assert_eq!(runtime.unseal(material), Ok(()));
        let Ok(id) = RequestId::parse("runtime-request-0002") else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"value".to_vec()) else { assert!(false); return; };
        let request = Request { id: id.clone(), namespace: NamespaceId::root(), token, now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value, cas: Some(0) } };
        assert!(matches!(runtime.execute(request), Err(RuntimeError::Control(ControlPlaneError::AuditOutcomeUnknown))));
        assert_eq!(runtime.state(), RuntimeState::RecoveryRequired); assert!(runtime.reconcile_request(&id).is_ok()); assert_eq!(runtime.state(), RuntimeState::Ready);
    }
}
'''


def recovery_providers_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::fmt;
use std::fs::{self, File, OpenOptions};
use std::io::{self, Read, Write};
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use heptabao_kms_contracts::{sha256, Digest32, KmsContractError, SecretMaterial};

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct RecoveryImageId(String);
impl RecoveryImageId {
    pub fn parse(value: &str) -> Result<Self, FileTargetError> {
        if value.len() < 8 || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte,b'-'|b'_')) { return Err(FileTargetError::InvalidId); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Eq, PartialEq)]
pub struct RecoveryImage { id: RecoveryImageId, bytes: SecretMaterial, digest: Digest32 }
impl RecoveryImage {
    pub fn new(id: RecoveryImageId, bytes: SecretMaterial) -> Self { let digest = sha256(bytes.expose()); Self { id, bytes, digest } }
    pub fn id(&self) -> &RecoveryImageId { &self.id }
    pub fn bytes(&self) -> &SecretMaterial { &self.bytes }
    pub fn digest(&self) -> Digest32 { self.digest }
}
impl fmt::Debug for RecoveryImage {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.debug_struct("RecoveryImage").field("id", &self.id).field("bytes_len", &self.bytes.len()).field("digest", &self.digest).finish() }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum FileTargetError { InvalidId, TargetNotEmpty, WriterBusy, Format, IntegrityMismatch, ProviderBeforeEntry(io::ErrorKind), OutcomeUnknownAfterEntry(io::ErrorKind), EmptyImage }

struct WriterLock { path: PathBuf }
impl WriterLock {
    fn acquire(root: &Path) -> Result<Self, FileTargetError> {
        let path = root.join(".writer-lock");
        match fs::create_dir(&path) {
            Ok(()) => Ok(Self { path }),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => Err(FileTargetError::WriterBusy),
            Err(error) => Err(FileTargetError::ProviderBeforeEntry(error.kind())),
        }
    }
}
impl Drop for WriterLock { fn drop(&mut self) { let _ = fs::remove_dir(&self.path); } }

pub struct StagedRecovery {
    root: PathBuf, id: RecoveryImageId, digest: Digest32, len: usize,
    staged_data: PathBuf, staged_meta: PathBuf, lock: Option<WriterLock>, published: bool,
}
impl Drop for StagedRecovery {
    fn drop(&mut self) {
        if !self.published { let _ = fs::remove_file(&self.staged_data); let _ = fs::remove_file(&self.staged_meta); }
        let _ = self.lock.take();
    }
}

#[derive(Clone, Eq, PartialEq)]
pub struct CurrentRecovery { pub id: RecoveryImageId, pub digest: Digest32, pub bytes: SecretMaterial }
impl fmt::Debug for CurrentRecovery {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.debug_struct("CurrentRecovery").field("id", &self.id).field("digest", &self.digest).field("bytes_len", &self.bytes.len()).finish() }
}

#[derive(Clone, Debug)]
pub struct FileRecoveryTarget { root: PathBuf }
impl FileRecoveryTarget {
    pub fn new(root: PathBuf) -> Self { Self { root } }
    pub fn root(&self) -> &Path { &self.root }
    pub fn stage_if_empty(&self, image: RecoveryImage) -> Result<StagedRecovery, FileTargetError> {
        if image.bytes.is_empty() { return Err(FileTargetError::EmptyImage); }
        fs::create_dir_all(&self.root).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        secure_directory(&self.root).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        let lock = WriterLock::acquire(&self.root)?;
        let mut entries = fs::read_dir(&self.root).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        while let Some(entry) = entries.next().transpose().map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))? {
            if entry.file_name() != ".writer-lock" { return Err(FileTargetError::TargetNotEmpty); }
        }
        let staged_data = self.root.join(format!("stage-{}.bin", image.id.as_str()));
        let staged_meta = self.root.join(format!("stage-{}.meta", image.id.as_str()));
        write_secure(&staged_data, image.bytes.expose()).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        let metadata = format!("id={}\ndigest={}\nlen={}\n", image.id.as_str(), image.digest.to_hex(), image.bytes.len());
        write_secure(&staged_meta, metadata.as_bytes()).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        sync_directory(&self.root).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        Ok(StagedRecovery { root: self.root.clone(), id: image.id, digest: image.digest, len: image.bytes.len(), staged_data, staged_meta, lock: Some(lock), published: false })
    }
    pub fn publish(&self, mut staged: StagedRecovery) -> Result<CurrentRecovery, FileTargetError> {
        if staged.root != self.root { return Err(FileTargetError::Format); }
        let final_data = self.root.join(format!("image-{}.bin", staged.id.as_str()));
        let final_meta = self.root.join(format!("image-{}.meta", staged.id.as_str()));
        let mut entered = false;
        if let Err(error) = fs::rename(&staged.staged_data, &final_data) { return Err(classify_publish(error, entered)); }
        entered = true;
        if let Err(error) = fs::rename(&staged.staged_meta, &final_meta) { return Err(classify_publish(error, entered)); }
        if let Err(error) = sync_directory(&self.root) { return Err(classify_publish(error, entered)); }
        let marker_tmp = self.root.join("CURRENT.tmp");
        let marker = format!("id={}\ndigest={}\nlen={}\n", staged.id.as_str(), staged.digest.to_hex(), staged.len);
        if let Err(error) = write_secure(&marker_tmp, marker.as_bytes()) { return Err(classify_publish(error, entered)); }
        if let Err(error) = fs::rename(&marker_tmp, self.root.join("CURRENT")) { return Err(classify_publish(error, entered)); }
        if let Err(error) = sync_directory(&self.root) { return Err(classify_publish(error, entered)); }
        let current = self.read_current()?;
        if current.id != staged.id || current.digest != staged.digest || current.bytes.len() != staged.len { return Err(FileTargetError::IntegrityMismatch); }
        staged.published = true; let _ = staged.lock.take(); Ok(current)
    }
    pub fn read_current(&self) -> Result<CurrentRecovery, FileTargetError> {
        let marker = fs::read_to_string(self.root.join("CURRENT")).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        let fields = parse_fields(&marker)?;
        let id = RecoveryImageId::parse(fields.get("id").ok_or(FileTargetError::Format)?)?;
        let digest = Digest32::parse_hex(fields.get("digest").ok_or(FileTargetError::Format)?).map_err(map_kms)?;
        let expected_len: usize = fields.get("len").ok_or(FileTargetError::Format)?.parse().map_err(|_| FileTargetError::Format)?;
        let mut file = File::open(self.root.join(format!("image-{}.bin", id.as_str()))).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        let mut bytes = Vec::new(); file.read_to_end(&mut bytes).map_err(|error| FileTargetError::ProviderBeforeEntry(error.kind()))?;
        if bytes.len() != expected_len || sha256(&bytes) != digest { return Err(FileTargetError::IntegrityMismatch); }
        let secret = SecretMaterial::new(bytes).map_err(map_kms)?;
        Ok(CurrentRecovery { id, digest, bytes: secret })
    }
}

fn map_kms(error: KmsContractError) -> FileTargetError { match error { KmsContractError::EmptySecret => FileTargetError::EmptyImage, _ => FileTargetError::Format } }
fn classify_publish(error: io::Error, entered: bool) -> FileTargetError { if entered { FileTargetError::OutcomeUnknownAfterEntry(error.kind()) } else { FileTargetError::ProviderBeforeEntry(error.kind()) } }
fn parse_fields(value: &str) -> Result<std::collections::BTreeMap<String,String>, FileTargetError> {
    let mut fields = std::collections::BTreeMap::new();
    for line in value.lines() { let Some((key, item)) = line.split_once('=') else { return Err(FileTargetError::Format); }; if fields.insert(key.to_owned(), item.to_owned()).is_some() { return Err(FileTargetError::Format); } }
    Ok(fields)
}
fn write_secure(path: &Path, bytes: &[u8]) -> io::Result<()> {
    let mut options = OpenOptions::new(); options.write(true).create_new(true);
    #[cfg(unix)] { use std::os::unix::fs::OpenOptionsExt; options.mode(0o600); }
    let mut file = options.open(path)?; file.write_all(bytes)?; file.sync_all()
}
fn secure_directory(path: &Path) -> io::Result<()> {
    #[cfg(unix)] { use std::os::unix::fs::PermissionsExt; fs::set_permissions(path, fs::Permissions::from_mode(0o700))?; }
    Ok(())
}
fn sync_directory(path: &Path) -> io::Result<()> { File::open(path)?.sync_all() }

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct AnchorId(String);
impl AnchorId { pub fn parse(value: &str) -> Result<Self, AnchorContractError> { if value.len() < 8 || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte,b'-'|b'_')) { Err(AnchorContractError::InvalidId) } else { Ok(Self(value.to_owned())) } } pub fn as_str(&self) -> &str { &self.0 } }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AnchorRecord { pub id: AnchorId, pub revision: u64, pub digest: Digest32 }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct FenceToken { nonce: u64, revision: u64 }
impl FenceToken { pub fn revision(&self) -> u64 { self.revision } }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AnchorContractError { InvalidId, RevisionOverflow, NotCurrent, Busy }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum BeginFenceError<E> { NotCurrent, Provider(E) }
#[derive(Clone, Debug, Eq, PartialEq)]
pub enum AnchorFenceError<O,E> { CheckpointNotCurrent, ProviderBeforeEntry(E), Operation(O), OutcomeUnknownAfterEntry(E) }
pub trait AnchorTransport {
    type Error;
    fn read_current(&self) -> Result<AnchorRecord, Self::Error>;
    fn begin_fence(&mut self, expected: &AnchorRecord) -> Result<FenceToken, BeginFenceError<Self::Error>>;
    fn complete_fence(&mut self, token: &FenceToken) -> Result<(), Self::Error>;
}
pub struct RemoteAnchorClient<T: AnchorTransport> { transport: T }
impl<T: AnchorTransport> RemoteAnchorClient<T> {
    pub fn new(transport: T) -> Self { Self { transport } }
    pub fn with_current_fence<R,O,F>(&mut self, expected: &AnchorRecord, operation: F) -> Result<R, AnchorFenceError<O,T::Error>> where F: FnOnce() -> Result<R,O> {
        let token = match self.transport.begin_fence(expected) { Ok(token) => token, Err(BeginFenceError::NotCurrent) => return Err(AnchorFenceError::CheckpointNotCurrent), Err(BeginFenceError::Provider(error)) => return Err(AnchorFenceError::ProviderBeforeEntry(error)) };
        let result = operation();
        if let Err(error) = self.transport.complete_fence(&token) { return Err(AnchorFenceError::OutcomeUnknownAfterEntry(error)); }
        result.map_err(AnchorFenceError::Operation)
    }
    pub fn read_current(&self) -> Result<AnchorRecord,T::Error> { self.transport.read_current() }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MemoryAnchorError { Busy, CompletionUnknown, NotCurrent, Poisoned }
#[derive(Debug)] struct MemoryAnchorState { current: AnchorRecord, active: Option<FenceToken>, next_nonce: u64 }
#[derive(Clone, Debug)] pub struct MemoryAnchorTransport { state: Arc<Mutex<MemoryAnchorState>>, fail_complete_once: bool }
impl MemoryAnchorTransport {
    pub fn new(current: AnchorRecord) -> Self { Self { state: Arc::new(Mutex::new(MemoryAnchorState { current, active: None, next_nonce: 1 })), fail_complete_once: false } }
    pub fn peer(&self) -> Self { Self { state: Arc::clone(&self.state), fail_complete_once: false } }
    pub fn fail_next_completion(&mut self) { self.fail_complete_once = true; }
    pub fn compare_and_swap(&mut self, expected: &AnchorRecord, next_digest: Digest32) -> Result<AnchorRecord,MemoryAnchorError> {
        let mut state = self.state.lock().map_err(|_| MemoryAnchorError::Poisoned)?;
        if state.active.is_some() { return Err(MemoryAnchorError::Busy); }
        if &state.current != expected { return Err(MemoryAnchorError::NotCurrent); }
        let revision = state.current.revision.checked_add(1).ok_or(MemoryAnchorError::NotCurrent)?;
        state.current = AnchorRecord { id: state.current.id.clone(), revision, digest: next_digest }; Ok(state.current.clone())
    }
}
impl AnchorTransport for MemoryAnchorTransport {
    type Error = MemoryAnchorError;
    fn read_current(&self) -> Result<AnchorRecord,Self::Error> { Ok(self.state.lock().map_err(|_| MemoryAnchorError::Poisoned)?.current.clone()) }
    fn begin_fence(&mut self, expected: &AnchorRecord) -> Result<FenceToken,BeginFenceError<Self::Error>> {
        let mut state = self.state.lock().map_err(|_| BeginFenceError::Provider(MemoryAnchorError::Poisoned))?;
        if state.active.is_some() { return Err(BeginFenceError::Provider(MemoryAnchorError::Busy)); }
        if &state.current != expected { return Err(BeginFenceError::NotCurrent); }
        let token = FenceToken { nonce: state.next_nonce, revision: state.current.revision }; state.next_nonce = state.next_nonce.wrapping_add(1); state.active = Some(token.clone()); Ok(token)
    }
    fn complete_fence(&mut self, token: &FenceToken) -> Result<(),Self::Error> {
        if self.fail_complete_once { self.fail_complete_once = false; return Err(MemoryAnchorError::CompletionUnknown); }
        let mut state = self.state.lock().map_err(|_| MemoryAnchorError::Poisoned)?;
        if state.active.as_ref() != Some(token) { return Err(MemoryAnchorError::NotCurrent); }
        state.active = None; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use std::sync::atomic::{AtomicU64,Ordering};
    use super::*;
    static COUNTER: AtomicU64 = AtomicU64::new(1);
    fn temp_root() -> PathBuf { std::env::temp_dir().join(format!("heptabao-recovery-provider-{}-{}",std::process::id(),COUNTER.fetch_add(1,Ordering::Relaxed))) }
    #[test]
    fn file_target_stages_only_empty_and_verifies_readback() {
        let root=temp_root(); let target=FileRecoveryTarget::new(root.clone());
        let Ok(id)=RecoveryImageId::parse("recovery-0001") else { assert!(false); return; }; let Ok(bytes)=SecretMaterial::new(b"recovery-bytes".to_vec()) else { assert!(false); return; };
        let image=RecoveryImage::new(id,bytes); let Ok(staged)=target.stage_if_empty(image) else { assert!(false); return; }; let Ok(current)=target.publish(staged) else { assert!(false); return; };
        assert_eq!(current.bytes.expose(),b"recovery-bytes");
        let Ok(id2)=RecoveryImageId::parse("recovery-0002") else { assert!(false); return; }; let Ok(bytes2)=SecretMaterial::new(b"other".to_vec()) else { assert!(false); return; };
        assert_eq!(target.stage_if_empty(RecoveryImage::new(id2,bytes2)).err(),Some(FileTargetError::TargetNotEmpty)); let _=fs::remove_dir_all(root);
    }
    #[test]
    fn corruption_is_rejected_and_concurrent_writer_is_fenced() {
        let root=temp_root(); let target=FileRecoveryTarget::new(root.clone());
        let Ok(id)=RecoveryImageId::parse("recovery-0003") else { assert!(false); return; }; let Ok(bytes)=SecretMaterial::new(b"bytes".to_vec()) else { assert!(false); return; };
        let Ok(staged)=target.stage_if_empty(RecoveryImage::new(id.clone(),bytes)) else { assert!(false); return; };
        let Ok(other_id)=RecoveryImageId::parse("recovery-0004") else { assert!(false); return; }; let Ok(other_bytes)=SecretMaterial::new(b"other".to_vec()) else { assert!(false); return; };
        assert_eq!(target.stage_if_empty(RecoveryImage::new(other_id,other_bytes)).err(),Some(FileTargetError::WriterBusy));
        let Ok(_)=target.publish(staged) else { assert!(false); return; }; assert!(fs::write(root.join(format!("image-{}.bin",id.as_str())),b"corrupt").is_ok()); assert_eq!(target.read_current().err(),Some(FileTargetError::IntegrityMismatch)); let _=fs::remove_dir_all(root);
    }
    #[test]
    fn anchor_lease_covers_operation_and_post_entry_failure_is_unknown() {
        let Ok(id)=AnchorId::parse("anchor-0001") else { assert!(false); return; }; let current=AnchorRecord { id, revision:1, digest:sha256(b"one") };
        let transport=MemoryAnchorTransport::new(current.clone()); let mut admin=transport.peer(); let mut client=RemoteAnchorClient::new(transport);
        let result=client.with_current_fence(&current,|| { assert_eq!(admin.compare_and_swap(&current,sha256(b"two")),Err(MemoryAnchorError::Busy)); Ok::<_,()>(7) }); assert_eq!(result,Ok(7));
        let mut uncertain=admin.peer(); uncertain.fail_next_completion(); let mut uncertain_client=RemoteAnchorClient::new(uncertain); let result=uncertain_client.with_current_fence(&current,||Ok::<_,()>(9)); assert_eq!(result,Err(AnchorFenceError::OutcomeUnknownAfterEntry(MemoryAnchorError::CompletionUnknown)));
    }
}
'''


def lifecycle_ops_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use heptabao_kms_contracts::Digest32;

fn valid_id(value:&str)->bool { value.len()>=8 && value.len()<=128 && value.bytes().all(|byte|byte.is_ascii_alphanumeric()||matches!(byte,b'-'|b'_')) }
#[derive(Clone,Debug,Eq,Hash,Ord,PartialEq,PartialOrd)] pub struct BackupId(String);
impl BackupId { pub fn parse(value:&str)->Result<Self,LifecycleError>{if valid_id(value){Ok(Self(value.to_owned()))}else{Err(LifecycleError::InvalidId)}} pub fn as_str(&self)->&str{&self.0} }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct BackupManifest { pub id:BackupId,pub source_generation:u64,pub source_digest:Digest32,pub size:u64,pub created_at_ms:u64 }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct UploadReceipt { pub location:String,pub digest:Digest32,pub verified_copies:u32,pub uploaded_at_ms:u64 }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct RetentionPolicy { pub minimum_verified_copies:u32,pub minimum_age_ms:u64 }
#[derive(Clone,Debug,Eq,PartialEq)] pub enum BackupState { Prepared,Uploaded(UploadReceipt),Verified(UploadReceipt),RetentionEligible(UploadReceipt),SourceDeleted(UploadReceipt) }
#[derive(Clone,Debug)] struct BackupRecord { manifest:BackupManifest,state:BackupState }
#[derive(Clone,Debug,Default)] pub struct BackupCatalog { records:BTreeMap<BackupId,BackupRecord> }

#[derive(Clone,Debug,Eq,PartialEq)] pub enum LifecycleError { InvalidId,Duplicate,Missing,InvalidTransition,DigestMismatch,InsufficientCopies,TooYoung,ClockOverflow,CursorRegression,WriterInvariant,OutcomeUnknown }
impl BackupCatalog {
    pub fn prepare(&mut self,manifest:BackupManifest)->Result<(),LifecycleError>{if manifest.size==0{return Err(LifecycleError::InvalidTransition)}if self.records.contains_key(&manifest.id){return Err(LifecycleError::Duplicate)}self.records.insert(manifest.id.clone(),BackupRecord{manifest,state:BackupState::Prepared});Ok(())}
    pub fn record_upload(&mut self,id:&BackupId,receipt:UploadReceipt)->Result<(),LifecycleError>{let record=self.records.get_mut(id).ok_or(LifecycleError::Missing)?;if !matches!(record.state,BackupState::Prepared){return Err(LifecycleError::InvalidTransition)}if receipt.digest!=record.manifest.source_digest{return Err(LifecycleError::DigestMismatch)}record.state=BackupState::Uploaded(receipt);Ok(())}
    pub fn verify_readback(&mut self,id:&BackupId,readback_digest:Digest32)->Result<(),LifecycleError>{let record=self.records.get_mut(id).ok_or(LifecycleError::Missing)?;let BackupState::Uploaded(receipt)=&record.state else{return Err(LifecycleError::InvalidTransition)};if receipt.digest!=readback_digest||receipt.digest!=record.manifest.source_digest{return Err(LifecycleError::DigestMismatch)}record.state=BackupState::Verified(receipt.clone());Ok(())}
    pub fn mark_retention_eligible(&mut self,id:&BackupId,now_ms:u64,policy:&RetentionPolicy)->Result<(),LifecycleError>{let record=self.records.get_mut(id).ok_or(LifecycleError::Missing)?;let BackupState::Verified(receipt)=&record.state else{return Err(LifecycleError::InvalidTransition)};if receipt.verified_copies<policy.minimum_verified_copies{return Err(LifecycleError::InsufficientCopies)}let age=now_ms.checked_sub(record.manifest.created_at_ms).ok_or(LifecycleError::ClockOverflow)?;if age<policy.minimum_age_ms{return Err(LifecycleError::TooYoung)}record.state=BackupState::RetentionEligible(receipt.clone());Ok(())}
    pub fn mark_source_deleted(&mut self,id:&BackupId)->Result<(),LifecycleError>{let record=self.records.get_mut(id).ok_or(LifecycleError::Missing)?;let BackupState::RetentionEligible(receipt)=&record.state else{return Err(LifecycleError::InvalidTransition)};record.state=BackupState::SourceDeleted(receipt.clone());Ok(())}
    pub fn state(&self,id:&BackupId)->Result<&BackupState,LifecycleError>{Ok(&self.records.get(id).ok_or(LifecycleError::Missing)?.state)}
}

#[derive(Clone,Debug,Eq,Hash,Ord,PartialEq,PartialOrd)] pub struct MigrationId(String);
impl MigrationId { pub fn parse(value:&str)->Result<Self,LifecycleError>{if valid_id(value){Ok(Self(value.to_owned()))}else{Err(LifecycleError::InvalidId)}} }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct EndpointIdentity { pub provider:String,pub instance:String,pub generation:u64 }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct MigrationPlan { pub id:MigrationId,pub source:EndpointIdentity,pub target:EndpointIdentity,pub expected_digest:Digest32 }
#[derive(Clone,Debug,Eq,PartialEq)] pub enum MigrationState { Planned,SourceFenced{epoch:u64},SnapshotCopied{epoch:u64,digest:Digest32},CatchingUp{epoch:u64,cursor:u64},CutoverPrepared{epoch:u64,cursor:u64},CutoverUnknown{epoch:u64,cursor:u64},CutoverComplete{target_epoch:u64},RollbackPrepared{source_epoch:u64},RolledBack{source_epoch:u64} }
#[derive(Clone,Debug,Eq,PartialEq)] pub enum CutoverDisposition { NotEntered,Committed{target_epoch:u64},OutcomeUnknown }
#[derive(Clone,Debug)] pub struct MigrationCoordinator { plan:MigrationPlan,state:MigrationState }
impl MigrationCoordinator {
    pub fn new(plan:MigrationPlan)->Result<Self,LifecycleError>{if plan.source==plan.target||plan.source.provider.is_empty()||plan.target.provider.is_empty(){return Err(LifecycleError::WriterInvariant)}Ok(Self{plan,state:MigrationState::Planned})}
    pub fn state(&self)->&MigrationState{&self.state}
    pub fn fence_source(&mut self,epoch:u64)->Result<(),LifecycleError>{if !matches!(self.state,MigrationState::Planned)||epoch<=self.plan.source.generation{return Err(LifecycleError::InvalidTransition)}self.state=MigrationState::SourceFenced{epoch};Ok(())}
    pub fn record_snapshot(&mut self,digest:Digest32)->Result<(),LifecycleError>{let MigrationState::SourceFenced{epoch}=self.state else{return Err(LifecycleError::InvalidTransition)};if digest!=self.plan.expected_digest{return Err(LifecycleError::DigestMismatch)}self.state=MigrationState::SnapshotCopied{epoch,digest};Ok(())}
    pub fn record_catch_up(&mut self,cursor:u64)->Result<(),LifecycleError>{let epoch=match self.state{MigrationState::SnapshotCopied{epoch,..}=>epoch,MigrationState::CatchingUp{epoch,cursor:previous}=>{if cursor<previous{return Err(LifecycleError::CursorRegression)}epoch},_=>return Err(LifecycleError::InvalidTransition)};self.state=MigrationState::CatchingUp{epoch,cursor};Ok(())}
    pub fn prepare_cutover(&mut self)->Result<(),LifecycleError>{let MigrationState::CatchingUp{epoch,cursor}=self.state else{return Err(LifecycleError::InvalidTransition)};self.state=MigrationState::CutoverPrepared{epoch,cursor};Ok(())}
    pub fn record_cutover(&mut self,disposition:CutoverDisposition)->Result<(),LifecycleError>{let MigrationState::CutoverPrepared{epoch,cursor}=self.state else{return Err(LifecycleError::InvalidTransition)};match disposition{CutoverDisposition::NotEntered=>{},CutoverDisposition::Committed{target_epoch}=>{if target_epoch<=epoch{return Err(LifecycleError::WriterInvariant)}self.state=MigrationState::CutoverComplete{target_epoch}},CutoverDisposition::OutcomeUnknown=>self.state=MigrationState::CutoverUnknown{epoch,cursor}}Ok(())}
    pub fn reconcile_cutover(&mut self,source_writable:bool,target_writable:bool,target_epoch:u64)->Result<(),LifecycleError>{let MigrationState::CutoverUnknown{epoch,..}=self.state else{return Err(LifecycleError::InvalidTransition)};if source_writable==target_writable{return Err(LifecycleError::WriterInvariant)}if target_writable{if target_epoch<=epoch{return Err(LifecycleError::WriterInvariant)}self.state=MigrationState::CutoverComplete{target_epoch}}else{self.state=MigrationState::SourceFenced{epoch}}Ok(())}
    pub fn prepare_rollback(&mut self,source_epoch:u64)->Result<(),LifecycleError>{let MigrationState::CutoverComplete{target_epoch}=self.state else{return Err(LifecycleError::InvalidTransition)};if source_epoch<=target_epoch{return Err(LifecycleError::WriterInvariant)}self.state=MigrationState::RollbackPrepared{source_epoch};Ok(())}
    pub fn complete_rollback(&mut self)->Result<(),LifecycleError>{let MigrationState::RollbackPrepared{source_epoch}=self.state else{return Err(LifecycleError::InvalidTransition)};self.state=MigrationState::RolledBack{source_epoch};Ok(())}
}

#[derive(Clone,Debug,Eq,PartialEq)] pub enum OpsCommand { Status,Seal,Unseal,BackupPrepare{backup_id:BackupId},BackupVerify{backup_id:BackupId},MigrationAdvance{migration_id:MigrationId},LeaseRevoke{lease_id:String},TokenRevoke{token_id:String} }
#[derive(Clone,Debug,Eq,PartialEq)] pub struct OpsEnvelope { pub operation_id:String,pub deadline_ms:u64,pub command:OpsCommand }
impl OpsEnvelope { pub fn new(operation_id:&str,deadline_ms:u64,command:OpsCommand)->Result<Self,LifecycleError>{if !valid_id(operation_id)||deadline_ms==0{return Err(LifecycleError::InvalidId)}Ok(Self{operation_id:operation_id.to_owned(),deadline_ms,command})} }

#[cfg(test)]
mod tests {
    use super::*; use heptabao_kms_contracts::sha256;
    #[test] fn backup_requires_digest_readback_copies_and_age(){let Ok(id)=BackupId::parse("backup-0001")else{assert!(false);return};let digest=sha256(b"state");let manifest=BackupManifest{id:id.clone(),source_generation:1,source_digest:digest,size:5,created_at_ms:10};let mut catalog=BackupCatalog::default();assert_eq!(catalog.prepare(manifest),Ok(()));let receipt=UploadReceipt{location:"offsite://one".to_owned(),digest,verified_copies:2,uploaded_at_ms:20};assert_eq!(catalog.record_upload(&id,receipt),Ok(()));assert_eq!(catalog.verify_readback(&id,digest),Ok(()));let policy=RetentionPolicy{minimum_verified_copies:2,minimum_age_ms:100};assert_eq!(catalog.mark_retention_eligible(&id,50,&policy),Err(LifecycleError::TooYoung));assert_eq!(catalog.mark_retention_eligible(&id,110,&policy),Ok(()));assert_eq!(catalog.mark_source_deleted(&id),Ok(()));}
    #[test] fn cutover_unknown_requires_single_writer_reconciliation(){let Ok(id)=MigrationId::parse("migration-0001")else{assert!(false);return};let plan=MigrationPlan{id,source:EndpointIdentity{provider:"source".to_owned(),instance:"a".to_owned(),generation:1},target:EndpointIdentity{provider:"target".to_owned(),instance:"b".to_owned(),generation:0},expected_digest:sha256(b"state")};let Ok(mut migration)=MigrationCoordinator::new(plan)else{assert!(false);return};assert_eq!(migration.fence_source(2),Ok(()));assert_eq!(migration.record_snapshot(sha256(b"state")),Ok(()));assert_eq!(migration.record_catch_up(9),Ok(()));assert_eq!(migration.prepare_cutover(),Ok(()));assert_eq!(migration.record_cutover(CutoverDisposition::OutcomeUnknown),Ok(()));assert_eq!(migration.reconcile_cutover(true,true,3),Err(LifecycleError::WriterInvariant));assert_eq!(migration.reconcile_cutover(false,true,3),Ok(()));assert_eq!(migration.state(),&MigrationState::CutoverComplete{target_epoch:3});}
}
'''


def module_doc(name: str, purpose: str, dependencies: str, invariants: list[str], gaps: list[str]) -> str:
    return f'''# `{name}` developer guide

## Purpose and responsibility

{purpose}

## Maturity and authority

Development source implementation. It is neither a qualified provider nor production authority.

## Dependency direction

{dependencies}

## Public API

Generated from exact source by Module Documentation V2.

## State model and invariants

''' + "\n".join(f"- {item}" for item in invariants) + '''

## Errors, failure classes, and retry semantics

Pre-entry failures guarantee the irreversible operation was not entered. Outcome-unknown failures require authoritative reconciliation and prohibit blind retry.

## Data formats and compatibility

All formats are internal V1.6 contracts. They do not establish storage, wire or OpenBao compatibility.

## Security considerations

Secret-bearing values use redacted Debug representations. Provider handles remain opaque. Exact digests, generations, epochs, leases and request identities are validated before state transitions.

## Testing strategy

Tests cover positive transitions, malformed identifiers, stale digests, writer overlap, concurrent fencing, corruption and outcome uncertainty.

## Extension rules

Provider integrations must preserve typed phase-aware failures and may not collapse an uncertain post-entry result into a safe retry classification.

## Operational guidance

Use only inside a reviewed composition root. External provider custody, platform qualification and incident procedures remain mandatory before production use.

## Known gaps

''' + "\n".join(f"- {item}" for item in gaps) + '''

## Traceability

- Plan: `docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md`
- Status: `planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml`
- Blockers: `planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml`
- Module truth: `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml`
'''


def module_renderer() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse,importlib.util
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
TRUTH_PATH=Path("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml")
PLAN_ID="HEPTABAO-PLAN-2026-09-02-V1.6.0"
SPEC=importlib.util.spec_from_file_location("v147",ROOT/"scripts/render_plan_v1_4_7.py");assert SPEC and SPEC.loader
BASE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(BASE);BASE.PLAN_ID=PLAN_ID;BASE.TRUTH_PATH=TRUTH_PATH

def value(root:Path)->dict:
    result=BASE.build_truth(root);result["schema"]="heptabao.module-source-truth.v3";result["plan_id"]=PLAN_ID;result.pop("baseline_commit",None);result.pop("baseline_tree",None);result["source_baseline"]=yaml.safe_load((root/"planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml").read_text())["source_baseline"];return result

def render(write:bool)->None:
    truth=value(ROOT);expected=BASE.dump_yaml(truth);path=ROOT/TRUTH_PATH
    if write:path.write_text(expected)
    elif not path.is_file() or path.read_text()!=expected:raise SystemExit("V1.6 module truth drift")
    for module in truth["modules"]:
        doc=ROOT/module["module_guide"];expected_doc=BASE.module_doc_expected(ROOT,module)
        if write:doc.write_text(expected_doc)
        elif doc.read_text()!=expected_doc:raise SystemExit(f"module guide drift: {doc}")
    index=ROOT/"docs/modules/README.md";text=index.read_text();begin="<!-- BEGIN V1.6.0 MODULE TRUTH INDEX -->";end="<!-- END V1.6.0 MODULE TRUTH INDEX -->"
    for old_begin,old_end in ((BASE.BEGIN_INDEX,BASE.END_INDEX),("<!-- BEGIN V1.5.0 MODULE TRUTH INDEX -->","<!-- END V1.5.0 MODULE TRUTH INDEX -->"),(begin,end)):
        if old_begin in text and old_end in text:
            start=text.index(old_begin);finish=text.index(old_end,start)+len(old_end);text=text[:start]+text[finish:]
    block=f'''{begin}\n## V1.6.0 machine-verified module truth\n\nThe current workspace contains `{truth["module_count"]}` source-bound crates. Run `python scripts/render_module_source_truth_v1_6_0.py --check`.\n{end}'''
    expected_index=text.rstrip()+"\n\n"+block+"\n"
    if write:index.write_text(expected_index)
    elif index.read_text()!=expected_index:raise SystemExit("module index drift")

def main()->int:
    parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument("--write",action="store_true");group.add_argument("--check",action="store_true");args=parser.parse_args();render(args.write);print("PASS V1.6.0 module truth");return 0
if __name__=="__main__":raise SystemExit(main())
'''


def successor_module_validator() -> str:
    baseline = repr(BASELINE_CRATES)
    return f'''#!/usr/bin/env python3
from __future__ import annotations
import tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
BASELINE={baseline}
EXEMPT={{"README.md","MODULE_DOCUMENTATION_STANDARD_V1.md","MODULE_DOCUMENTATION_STANDARD_V2.md"}}

def members()->dict[str,Path]:
    data=tomllib.loads((ROOT/"Cargo.toml").read_text());result={{}}
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path/"Cargo.toml").is_file():result[tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"]]=path
    return result

def main()->int:
    workspace=members();names=set(workspace);missing=BASELINE-names
    if missing:raise SystemExit(f"prior crate disappeared: {{sorted(missing)}}")
    candidates=[ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml",ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml",ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml"]
    truth_path=next((path for path in candidates if path.is_file()),None)
    if truth_path is None:raise SystemExit("module truth missing")
    truth=yaml.safe_load(truth_path.read_text());truth_names={{item["crate"] for item in truth["modules"]}}
    if truth_names!=names or truth["module_count"]!=len(names):raise SystemExit("module truth/workspace mismatch")
    docs=ROOT/"docs/modules"
    for name in sorted(names):
        path=docs/f"{{name}}.md"
        if not path.is_file():raise SystemExit(f"missing module guide: {{name}}")
        text=path.read_text()
        for token in ("## Public API","BEGIN GENERATED V1.4.7 PUBLIC API TRUTH","BEGIN GENERATED V1.4.7 MODULE FACTS","## Known gaps","## Traceability"):
            if token not in text:raise SystemExit(f"{{name}} missing {{token}}")
    orphan={{path.name for path in docs.glob("*.md") if path.name not in EXEMPT and path.stem not in names}}
    if orphan:raise SystemExit(f"orphan module guides: {{sorted(orphan)}}")
    print(f"PASS successor module documentation: {{len(names)}} crates")
    return 0
if __name__=="__main__":raise SystemExit(main())
'''


def v150_successor_validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import subprocess,tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
REQUIRED={"heptabao-namespace","heptabao-policy","heptabao-identity","heptabao-token","heptabao-lease","heptabao-system","heptabao-plugin-contracts","heptabao-kv","heptabao-control-plane"}
CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def main()->int:
    for path in ("planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml","planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml","docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md"):
        if not (ROOT/path).is_file():raise SystemExit(f"missing inherited V1.5 object: {path}")
    status=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml").read_text());blockers=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml").read_text())
    if status["claims"]!=CLAIMS or blockers["claims"]!=CLAIMS:raise SystemExit("V1.5 authority drift")
    subprocess.run(["git","merge-base","--is-ancestor",status["source_baseline"]["commit"],"HEAD"],cwd=ROOT,check=True)
    data=tomllib.loads((ROOT/"Cargo.toml").read_text());names=set()
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path/"Cargo.toml").is_file():names.add(tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"])
    if not REQUIRED.issubset(names):raise SystemExit("V1.5 domain crate disappeared")
    current=(ROOT/"docs/CURRENT_DOCUMENTATION.md").read_text()
    if "HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md" not in current and "HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md" not in current:raise SystemExit("current documentation lost V1.5 lineage")
    print("PASS inherited V1.5 control-plane lineage")
    return 0
if __name__=="__main__":raise SystemExit(main())
'''


def v150_successor_tests() -> str:
    return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class V150SuccessorTests(unittest.TestCase):
    def test_v150_repository_receipt_never_closes_external_scope(self)->None:
        value=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
        self.assertEqual([],value["external_or_control_blockers_closed"]);self.assertEqual("NONE",value["claims"]["authority_effect"])
    def test_v150_domain_crates_remain_in_current_truth(self)->None:
        truth=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml").read_text());names={item["crate"] for item in truth["modules"]}
        self.assertTrue({"heptabao-namespace","heptabao-policy","heptabao-identity","heptabao-token","heptabao-lease","heptabao-system","heptabao-plugin-contracts","heptabao-kv","heptabao-control-plane"}.issubset(names))
if __name__=="__main__":unittest.main()
'''


def plan_doc(baseline: str, tree: str) -> str:
    return f'''# HeptaBao Plan V1.6.0 — Runtime, Recovery Providers, and Operations

## Baseline

This tranche starts from reviewed V1.5.0 integration commit `{baseline}`, tree `{tree}`.

## Objectives

1. introduce opaque KMS/HSM handles, standardized SHA-256 source binding, redacted secret material and phase-aware provider errors;
2. create a sealed runtime composition root that is the only request entry point and moves to recovery-required after possible effects;
3. implement an owner-only file recovery target with atomic empty admission, writer fencing, durable staging, publication marker, readback and corruption rejection;
4. implement a lease-backed remote-anchor client and deterministic server model that holds currentness across the supplied operation and reports post-entry completion uncertainty;
5. implement backup verification/retention and online migration/cutover state machines;
6. define typed operations envelopes for seal, unseal, backup, migration, lease and token administration;
7. extend source-bound module truth and exact-head/prospective-merge regression to the expanded workspace.

## Security and durability rules

Secret bytes never appear in Debug output. KMS private material is represented only by opaque handles. File recovery admission checks emptiness while holding a writer directory lock; any orphan left by a crash blocks new staging. Publication creates immutable image files before atomically replacing `CURRENT`, synchronizes the containing directory, and verifies readback digest and length. A failure after the first irreversible rename is outcome unknown.

Remote anchor begin-fence atomically compares the expected record and acquires a lease. Compare-and-swap is rejected while that lease is active. Completion failure after the operation closure entered is `OutcomeUnknownAfterEntry` and cannot be relabelled as a safe pre-entry provider error.

The runtime accepts requests only in `Ready`. Audit/control-plane uncertainty moves the entire runtime to `RecoveryRequired`; no further request is accepted until the exact request is reconciled.

## Repository blockers

`HB-BLK-REPO-072..078` cover KMS contracts, runtime composition, file recovery target, remote anchor fencing, backup/retention, migration/ops and successor validation. They remain review-required until exact head, prospective merge and independent review complete.

## External boundary

No source implementation qualifies an HSM, filesystem/controller profile, remote service, offsite custody, migration deployment, 24x7 operations or release. `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open.

## Required gates

```text
python scripts/render_module_source_truth_v1_6_0.py --check
python scripts/validate_plan_v1_6_0.py
python scripts/validate_plan_v1_5_0.py
python scripts/validate_plan_v1_4_7.py
python scripts/validate_plan_v1_4_6.py
python scripts/validate_plan_v1_4_5.py
python scripts/validate_module_documentation_v1_4_4.py
python -m unittest discover -s tests/plan -p 'test_*.py' -v
python -m unittest discover -s tests/platform -p 'test_*.py' -v
python -m unittest discover -s tests/oracle -p 'test_*.py' -v
cargo +1.98.0 fmt --all -- --check
cargo +1.98.0 test --locked --workspace --all-targets
cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
```
'''


def current_docs() -> str:
    return '''# HeptaBao Current Documentation

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md` |
| current status | `planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_6_0.yaml` |
| module truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml` |
| runtime architecture | `docs/architecture/HEPTABAO_RUNTIME_RECOVERY_OPERATIONS_V1.md` |
| V1.5 post-merge receipt | `planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| current gate | `.github/workflows/plan-v1.6.0-runtime-recovery-operations.yml` |

## Inherited normative set

V1.5.0 control-plane documents and all V1.4.7/V1.4.6/V1.4.5 recovery, security, module and external-admission contracts remain inherited immutable evidence. Successor validators require their source lineage and fail-closed authority flags.

## Supersession chain

```text
V1.4.7 post-merge truth and external admission
  → V1.5.0 control-plane vertical slice
  → V1.6.0 runtime, recovery providers and operations
```

## Current implementation scope

The workspace now includes a sealed runtime composition root, opaque KMS/HSM contracts, a durable file recovery target, a lease-backed remote-anchor client, backup retention, migration and operations state machines in addition to the V1.5 control plane and inherited recovery kernel.

These are development source implementations and conformance models. No real HSM custody, remote anchor service, qualified filesystem/controller, offsite backup, production migration, incident operation or compatibility claim follows from repository success.

## Open authority boundary

`HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open. Qualification, compatibility, provider selection and production/migration/release authority remain false.
'''


def architecture_doc() -> str:
    return '''# HeptaBao Runtime, Recovery, and Operations Architecture V1

## Runtime lifecycle

```text
Bootstrap → Sealed → Unsealing → Ready ↔ Draining
                         │          │
                         └──────────┴→ RecoveryRequired
Ready/Draining → Sealed → Stopped
```

Only `Ready` accepts a request. A possible post-effect outcome moves the runtime to `RecoveryRequired`; the exact request ID must be reconciled before returning to `Ready`.

## Provider topology

- KMS/HSM contracts expose opaque handles and phase-aware errors; they contain no production provider selection.
- File recovery target owns an isolated directory, owner-only files, a writer lock, staged image, immutable image pair and atomic `CURRENT` marker.
- Remote anchor client obtains a server lease before invoking the publication closure. The same server-side exclusion blocks compare-and-swap until fence completion.
- Backup source deletion requires matching upload/readback digest, minimum verified copies and minimum age.
- Migration cutover requires source fencing, exact snapshot digest, monotonic catch-up cursor and single-writer reconciliation after uncertainty.

## Retry taxonomy

A before-entry provider error can be retried after correcting the provider condition. Once publication, cutover or a supplied operation may have entered, uncertainty is preserved and both authoritative sides must be inspected before retry.
'''


def status_doc(baseline: str, tree: str) -> dict[str, Any]:
    return {
        "schema":"heptabao.v1-6-0-runtime-operations-status.v1","plan_id":PLAN_ID,"revision":"1.6.0",
        "status":"SOURCE_IMPLEMENTED_EXACT_HEAD_MERGE_AND_INDEPENDENT_REVIEW_REQUIRED",
        "current_plan":"docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md",
        "current_blocker_register":"planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml",
        "normative_manifest":"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_6_0.yaml",
        "source_baseline":{"commit":baseline,"tree":tree},
        "closed_repository_scope_carried_forward":[f"HB-BLK-REPO-{i:03d}" for i in range(49,72)],
        "implementation":{"kms_hsm_contracts":"IMPLEMENTED_SOURCE","runtime_composition_root":"IMPLEMENTED_SOURCE","file_recovery_target":"IMPLEMENTED_SOURCE","remote_anchor_protocol":"IMPLEMENTED_SOURCE","backup_retention_state_machine":"IMPLEMENTED_SOURCE","migration_and_ops_state_machine":"IMPLEMENTED_SOURCE","successor_module_truth":"IMPLEMENTED_SOURCE"},
        "repository_open":[f"HB-BLK-REPO-{i:03d}" for i in range(72,79)],
        "external_open":["HB-BLK-CTRL-001",*[f"HB-BLK-EXT-{i:03d}" for i in range(1,8)]],
        "product_gaps_carried_forward":["real KMS or HSM provider qualification and custody","remote anchor service deployment qualification","filesystem and storage-controller power-cut qualification","offsite backup custody and restore drills","production online migration and mixed-version operation","Raft HA replication membership and snapshots","HTTP TLS CLI Agent Proxy and plugin process host","full OpenBao compatibility and restricted Oracle transfer"],
        "claims":CLAIMS,
    }


def blockers_doc(baseline: str, tree: str) -> dict[str, Any]:
    titles=["opaque KMS HSM contracts and phase-aware failures were absent","no sealed runtime composition root enforced the control plane","no atomic owner-only file recovery target existed","no lease-backed remote rollback-anchor client preserved post-entry uncertainty","backup verification retention and source deletion state was absent","migration cutover rollback and operations envelopes were absent","expanded runtime workspace lacked successor truth and exact head merge closure"]
    evidence=[["crates/heptabao-kms-contracts"],["crates/heptabao-runtime"],["crates/heptabao-recovery-providers"],["crates/heptabao-recovery-providers"],["crates/heptabao-lifecycle-ops"],["crates/heptabao-lifecycle-ops"],["planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml",".github/workflows/plan-v1.6.0-runtime-recovery-operations.yml"]]
    added=[]
    for number,title in enumerate(titles,72):added.append({"id":f"HB-BLK-REPO-{number:03d}","class":"REPOSITORY_CONTROLLED","severity":"CRITICAL" if number in {72,73,74,75} else "HIGH","title":title,"state":"IMPLEMENTED_SOURCE_REVIEW_REQUIRED","closure_criteria":["typed implementation and hostile tests exist","phase-aware uncertainty is not relabelled safe","module source truth is current","exact head and prospective merge pass before closure"],"evidence":evidence[number-72],"closure_receipt_required":True})
    return {"schema":"heptabao.blocker-register-extension.v1_6_0","plan_id":PLAN_ID,"revision":"1.6.0","status":"ACTIVE_FAIL_CLOSED","inherits":"planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml","source_baseline":{"commit":baseline,"tree":tree},"closed_carried_forward":[{"id":f"HB-BLK-REPO-{i:03d}","state":"CLOSED_REPOSITORY_SCOPE"} for i in range(49,72)],"added_blockers":added,"external_and_control_blockers_carried_forward":["HB-BLK-CTRL-001",*[f"HB-BLK-EXT-{i:03d}" for i in range(1,8)]],"product_gaps_carried_forward":status_doc(baseline,tree)["product_gaps_carried_forward"],"claims":CLAIMS}


def post_merge_receipt(baseline: str, tree: str, head: str) -> dict[str, Any]:
    return {"schema":"heptabao.repository-post-merge-closure-receipt.v1","plan_id":PLAN_ID,"repository":{"id":1349115072,"full_name":"TrillionniumFoundation/HeptaBao"},"pull_request":64,"reviewed_head_commit":head,"merge_commit":baseline,"merge_tree":tree,"required_reviewers":["ProfHepta","Tomasrgbsf"],"required_workflow_families":["V1.5.0","V1.4.7","V1.4.6","V1.4.5","V1.4.4"],"administrator_bypass":False,"closed_repository_blockers":[f"HB-BLK-REPO-{i:03d}" for i in range(63,72)],"external_or_control_blockers_closed":[],"claims":CLAIMS}


def plan_validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations
import hashlib,subprocess,tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1]
NEW={"heptabao-kms-contracts","heptabao-runtime","heptabao-recovery-providers","heptabao-lifecycle-ops"}
CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
    status=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml").read_text());blockers=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml").read_text());receipt=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
    for value in (status,blockers,receipt):
        if value["claims"]!=CLAIMS:raise SystemExit("authority drift")
    baseline=status["source_baseline"];tree=subprocess.check_output(["git","rev-parse",f"{baseline['commit']}^{{tree}}"],cwd=ROOT,text=True).strip()
    if tree!=baseline["tree"]:raise SystemExit("baseline tree drift")
    subprocess.run(["git","merge-base","--is-ancestor",baseline["commit"],"HEAD"],cwd=ROOT,check=True)
    data=tomllib.loads((ROOT/"Cargo.toml").read_text());names=set()
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path/"Cargo.toml").is_file():names.add(tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"])
    if not NEW.issubset(names):raise SystemExit(f"new crate missing: {sorted(NEW-names)}")
    truth=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml").read_text())
    if {item["crate"] for item in truth["modules"]}!=names:raise SystemExit("module truth mismatch")
    if [item["id"] for item in blockers["added_blockers"]]!=[f"HB-BLK-REPO-{i:03d}" for i in range(72,79)]:raise SystemExit("blocker set mismatch")
    source=(ROOT/"crates/heptabao-recovery-providers/src/lib.rs").read_text()
    for token in ("stage_if_empty","OutcomeUnknownAfterEntry","begin_fence","complete_fence","IntegrityMismatch","WriterBusy"):
        if token not in source:raise SystemExit(f"provider invariant missing: {token}")
    runtime=(ROOT/"crates/heptabao-runtime/src/lib.rs").read_text()
    for token in ("RuntimeState::RecoveryRequired","reconcile_request","RuntimeState::Ready","RuntimeState::Sealed"):
        if token not in runtime:raise SystemExit(f"runtime invariant missing: {token}")
    workflow=(ROOT/".github/workflows/plan-v1.6.0-runtime-recovery-operations.yml").read_text()
    if "pull_request:" not in workflow or "push:" in workflow or "prospective-merge" not in workflow:raise SystemExit("workflow drift")
    manifest=yaml.safe_load((ROOT/"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_6_0.yaml").read_text())
    for item in manifest["files"]:
        path=ROOT/item["path"]
        if not path.is_file() or sha(path)!=item["sha256"]:raise SystemExit(f"manifest mismatch: {item['path']}")
    subprocess.run(["python","scripts/render_module_source_truth_v1_6_0.py","--check"],cwd=ROOT,check=True)
    print("PASS HeptaBao V1.6.0 runtime recovery and operations")
    return 0
if __name__=="__main__":raise SystemExit(main())
'''


def plan_tests() -> str:
    return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class PlanV160Tests(unittest.TestCase):
    def test_repository_blockers_and_external_boundary(self)->None:
        value=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml").read_text());self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(72,79)],[item["id"] for item in value["added_blockers"]]);self.assertIn("HB-BLK-EXT-007",value["external_and_control_blockers_carried_forward"]);self.assertEqual("NONE",value["claims"]["authority_effect"])
    def test_v150_receipt_closes_only_repository_scope(self)->None:
        value=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text());self.assertEqual([],value["external_or_control_blockers_closed"]);self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(63,72)],value["closed_repository_blockers"])
    def test_module_truth_contains_runtime_provider_domains(self)->None:
        value=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml").read_text());names={item["crate"] for item in value["modules"]};self.assertTrue({"heptabao-kms-contracts","heptabao-runtime","heptabao-recovery-providers","heptabao-lifecycle-ops"}.issubset(names))
if __name__=="__main__":unittest.main()
'''


def workflow() -> str:
    return '''name: HeptaBao V1.6.0 runtime recovery operations

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches:
      - integration/v1.4.4-technical-candidate

permissions:
  contents: read

concurrency:
  group: v1.6.0-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
  cancel-in-progress: true

jobs:
  validate:
    name: v1.6.0 / pull_request / ${{ matrix.source_kind }}
    runs-on: ubuntu-24.04
    timeout-minutes: 180
    strategy:
      fail-fast: false
      matrix:
        source_kind: [exact-head, prospective-merge]
    env:
      SOURCE_KIND: ${{ matrix.source_kind }}
      SOURCE_SHA: ${{ matrix.source_kind == 'prospective-merge' && github.sha || github.event.pull_request.head.sha }}
      HEAD_SHA: ${{ github.event.pull_request.head.sha }}
      BASE_SHA: ${{ github.event.pull_request.base.sha }}
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ env.SOURCE_SHA }}
          fetch-depth: 0
          persist-credentials: false
      - name: Bind source identity
        shell: bash
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
          if [[ "$SOURCE_KIND" == prospective-merge ]];then read -r merge first second extra <<<"$(git rev-list --parents -n 1 HEAD)";test "$merge" = "$SOURCE_SHA";test "$first" = "$BASE_SHA";test "$second" = "$HEAD_SHA";test -z "${extra:-}";else test "$SOURCE_SHA" = "$HEAD_SHA";fi
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-plan.txt
      - name: Validate current and inherited plans
        shell: bash
        run: |
          set -euo pipefail
          python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
          python scripts/render_module_source_truth_v1_6_0.py --check
          python scripts/validate_plan_v1_6_0.py
          python scripts/validate_plan_v1_5_0.py
          python scripts/validate_plan_v1_4_7.py
          python scripts/validate_plan_v1_4_6.py
          python scripts/validate_plan_v1_4_5.py
          python scripts/validate_module_documentation_v1_4_4.py
          python -m unittest discover -s tests/plan -p 'test_*.py' -v
          python -m unittest discover -s tests/platform -p 'test_*.py' -v
          python -m unittest discover -s tests/oracle -p 'test_*.py' -v
      - name: Install Rust 1.98
        shell: bash
        run: rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
      - name: Validate locked workspace
        shell: bash
        run: |
          set -euo pipefail
          cargo +1.98.0 fmt --all -- --check
          cargo +1.98.0 test --locked --workspace --all-targets
          cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
'''


def standard_v2() -> str:
    return '''# HeptaBao Module Documentation Standard V2

Every current Cargo workspace crate has exactly one guide under `docs/modules/`. Cargo/source SHA-256, workspace-internal dependencies, public lexical declarations and discovered tests are generated into the current `planning/HEPTABAO_MODULE_SOURCE_TRUTH_*.yaml` and guide blocks. Historical coverage remains immutable evidence; successor validation requires every inherited crate to remain and every added crate to satisfy the same standard.

The current renderer is `python scripts/render_module_source_truth_v1_6_0.py --check`. The inventory is bounded lexical source truth, not Rust name resolution, compatibility, platform qualification or authority.
'''


def materialize(root: Path) -> None:
    baseline=sh(root,"git","rev-parse","HEAD");tree=sh(root,"git","rev-parse","HEAD^{tree}");parents=sh(root,"git","rev-list","--parents","-n","1","HEAD").split();head=parents[2] if len(parents)>2 else baseline
    update_workspace(root)
    crates={
        "heptabao-kms-contracts":(kms_rs(),{}),
        "heptabao-runtime":(runtime_rs(),{"heptabao-control-plane":"../heptabao-control-plane","heptabao-identity":"../heptabao-identity","heptabao-kms-contracts":"../heptabao-kms-contracts","heptabao-kv":"../heptabao-kv","heptabao-namespace":"../heptabao-namespace","heptabao-policy":"../heptabao-policy","heptabao-system":"../heptabao-system","heptabao-token":"../heptabao-token"}),
        "heptabao-recovery-providers":(recovery_providers_rs(),{"heptabao-kms-contracts":"../heptabao-kms-contracts"}),
        "heptabao-lifecycle-ops":(lifecycle_ops_rs(),{"heptabao-kms-contracts":"../heptabao-kms-contracts"}),
    }
    guides={
        "heptabao-kms-contracts":("Define opaque KMS/HSM handles, redacted secret material, SHA-256 digest binding and phase-aware provider contracts.","No workspace dependencies.",["Private key bytes never enter the contract.","Post-entry provider uncertainty is explicit.","Digest parsing accepts only exact lowercase hex."],["No selected or qualified production provider, HSM custody or zeroization guarantee."]),
        "heptabao-runtime":("Own the sealed runtime lifecycle and make the V1.5 control plane the only request entry point.","Depends on the control plane and typed domain crates.",["Only Ready accepts requests.","Possible effects move the runtime to RecoveryRequired.","Sealing removes the active seal capability."],["No network listener, process supervisor or production seal provider."]),
        "heptabao-recovery-providers":("Provide a durable file recovery target and lease-backed remote anchor protocol model.","Depends only on KMS digest and secret types.",["Empty-target admission occurs under a writer lock.","CURRENT is published after immutable image files and directory sync.","Anchor lease covers the supplied operation.","Post-entry completion failure is outcome unknown."],["No qualified filesystem/controller profile or deployed remote service."]),
        "heptabao-lifecycle-ops":("Model backup retention, migration cutover/rollback and typed operations envelopes.","Depends on exact digest types.",["Source deletion requires verified copies and age.","Migration uncertainty requires single-writer reconciliation.","Catch-up cursor never regresses."],["No offsite backend, restore execution, mixed-version transport or command-line client."]),
    }
    for name,(source,deps) in crates.items():write(root,f"crates/{name}/Cargo.toml",crate_toml(name,deps));write(root,f"crates/{name}/src/lib.rs",source);write(root,f"docs/modules/{name}.md",module_doc(name,*guides[name]))
    write(root,"scripts/render_module_source_truth_v1_6_0.py",module_renderer());write(root,"scripts/validate_module_documentation_v1_4_4.py",successor_module_validator());write(root,"scripts/validate_plan_v1_5_0.py",v150_successor_validator());write(root,"tests/plan/test_plan_v1_5_0.py",v150_successor_tests());write(root,"docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md",standard_v2())
    write(root,"docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md",plan_doc(baseline,tree));write(root,"docs/architecture/HEPTABAO_RUNTIME_RECOVERY_OPERATIONS_V1.md",architecture_doc());write(root,"planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml",yaml.safe_dump(status_doc(baseline,tree),sort_keys=False,width=120));write(root,"planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml",yaml.safe_dump(blockers_doc(baseline,tree),sort_keys=False,width=120));write(root,"planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml",yaml.safe_dump(post_merge_receipt(baseline,tree,head),sort_keys=False,width=120));write(root,"docs/CURRENT_DOCUMENTATION.md",current_docs());write(root,".github/workflows/plan-v1.6.0-runtime-recovery-operations.yml",workflow());write(root,"scripts/validate_plan_v1_6_0.py",plan_validator());write(root,"tests/plan/test_plan_v1_6_0.py",plan_tests())
    subprocess.run(["python","scripts/render_module_source_truth_v1_6_0.py","--write"],cwd=root,check=True)
    truth=yaml.safe_load((root/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml").read_text())
    normative=["docs/CURRENT_DOCUMENTATION.md","docs/plan/HEPTABAO_PLAN_V1_6_0_RUNTIME_RECOVERY_AND_OPERATIONS.md","docs/architecture/HEPTABAO_RUNTIME_RECOVERY_OPERATIONS_V1.md","docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md","planning/HEPTABAO_V1_6_0_RUNTIME_OPERATIONS_STATUS.yaml","planning/HEPTABAO_BLOCKER_REGISTER_V1_6_0.yaml","planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_6_0.yaml","planning/evidence/repository/HEPTABAO_V1_5_0_POST_MERGE_CLOSURE_RECEIPT.yaml","scripts/render_module_source_truth_v1_6_0.py","scripts/validate_plan_v1_6_0.py",".github/workflows/plan-v1.6.0-runtime-recovery-operations.yml"]+[item["module_guide"] for item in truth["modules"]]
    manifest={"schema":"heptabao.normative-document-manifest.v1_6_0","plan_id":PLAN_ID,"revision":"1.6.0","status":"CANDIDATE_EXACT_HEAD_MERGE_REVIEW_REQUIRED","source_baseline":{"commit":baseline,"tree":tree},"files":[{"path":path,"sha256":file_sha(root/path)} for path in sorted(set(normative))],"claims":CLAIMS};write(root,"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_6_0.yaml",yaml.safe_dump(manifest,sort_keys=False,width=120))

def main()->int:
    parser=argparse.ArgumentParser();parser.add_argument("root",type=Path);args=parser.parse_args();materialize(args.root.resolve());return 0
if __name__=="__main__":raise SystemExit(main())
