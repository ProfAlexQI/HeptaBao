#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import textwrap
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ID = 1349115072
REPO = "TrillionniumFoundation/HeptaBao"
PLAN_ID = "HEPTABAO-PLAN-2026-09-02-V1.5.0"
NEW_CRATES = [
    "heptabao-namespace",
    "heptabao-policy",
    "heptabao-identity",
    "heptabao-token",
    "heptabao-lease",
    "heptabao-system",
    "heptabao-plugin-contracts",
    "heptabao-kv",
    "heptabao-control-plane",
]
BASELINE_CRATES = [
    "heptabao-authbus-contracts", "heptabao-barrier-api", "heptabao-durable-core",
    "heptabao-filesystem-guard", "heptabao-governance", "heptabao-journal-api",
    "heptabao-journaled-core", "heptabao-key-lifecycle", "heptabao-operation-ledger",
    "heptabao-oracle-observer", "heptabao-p0-server", "heptabao-platform-bakeoff",
    "heptabao-platform-contracts", "heptabao-protocol", "heptabao-recovery-core",
    "heptabao-rollback-anchor", "heptabao-single-node-journal", "heptabao-single-node-store",
    "heptabao-storage-api",
]
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


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(root: Path, path: str, content: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content.rstrip() + "\n", encoding="utf-8")


def crate_toml(name: str, dependencies: dict[str, str] | None = None) -> str:
    lines = [
        "[package]", f'name = "{name}"', 'version = "0.1.0"', 'edition = "2024"',
        'rust-version = "1.98"', "publish = false", "", "[lints]", "workspace = true",
    ]
    if dependencies:
        lines.extend(["", "[dependencies]"])
        for dependency, path in dependencies.items():
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
        separator = "" if body.endswith("\n") else "\n"
        body = body + separator + "".join(f'  "{item}",\n' for item in additions)
        text = text[: match.start(2)] + body + text[match.end(2) :]
        path.write_text(text, encoding="utf-8")


def namespace_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::BTreeMap;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct NamespaceId(String);

impl NamespaceId {
    pub fn parse(value: &str) -> Result<Self, NamespaceError> {
        if value.is_empty() || value.len() > 64 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')) {
            return Err(NamespaceError::InvalidId);
        }
        Ok(Self(value.to_owned()))
    }

    pub fn root() -> Self {
        Self("root".to_owned())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub struct NamespacePath(String);

impl NamespacePath {
    pub fn parse(value: &str) -> Result<Self, NamespaceError> {
        if value == "/" {
            return Ok(Self(value.to_owned()));
        }
        if !value.starts_with('/') || value.ends_with('/') || value.len() > 1_024 {
            return Err(NamespaceError::InvalidPath);
        }
        for segment in value[1..].split('/') {
            if segment.is_empty() || segment == "." || segment == ".." || segment.len() > 64
                || !segment.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
            {
                return Err(NamespaceError::InvalidPath);
            }
        }
        Ok(Self(value.to_owned()))
    }

    pub fn root() -> Self {
        Self("/".to_owned())
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }

    pub fn parent(&self) -> Option<Self> {
        if self.0 == "/" {
            return None;
        }
        let index = self.0.rfind('/')?;
        if index == 0 {
            Some(Self::root())
        } else {
            Some(Self(self.0[..index].to_owned()))
        }
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct NamespaceRecord {
    id: NamespaceId,
    path: NamespacePath,
    parent: Option<NamespaceId>,
    active: bool,
}

impl NamespaceRecord {
    pub fn id(&self) -> &NamespaceId { &self.id }
    pub fn path(&self) -> &NamespacePath { &self.path }
    pub fn parent(&self) -> Option<&NamespaceId> { self.parent.as_ref() }
    pub fn is_active(&self) -> bool { self.active }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum NamespaceError {
    InvalidId,
    InvalidPath,
    DuplicateId,
    DuplicatePath,
    ParentMissing,
    NotFound,
    Inactive,
    RootImmutable,
}

#[derive(Clone, Debug)]
pub struct NamespaceRegistry {
    by_id: BTreeMap<NamespaceId, NamespaceRecord>,
    by_path: BTreeMap<NamespacePath, NamespaceId>,
}

impl Default for NamespaceRegistry {
    fn default() -> Self {
        let id = NamespaceId::root();
        let path = NamespacePath::root();
        let record = NamespaceRecord { id: id.clone(), path: path.clone(), parent: None, active: true };
        let mut by_id = BTreeMap::new();
        let mut by_path = BTreeMap::new();
        by_id.insert(id.clone(), record);
        by_path.insert(path, id);
        Self { by_id, by_path }
    }
}

impl NamespaceRegistry {
    pub fn create(&mut self, id: NamespaceId, path: NamespacePath) -> Result<NamespaceRecord, NamespaceError> {
        if self.by_id.contains_key(&id) { return Err(NamespaceError::DuplicateId); }
        if self.by_path.contains_key(&path) { return Err(NamespaceError::DuplicatePath); }
        let parent_path = path.parent().ok_or(NamespaceError::RootImmutable)?;
        let parent_id = self.by_path.get(&parent_path).cloned().ok_or(NamespaceError::ParentMissing)?;
        let parent = self.by_id.get(&parent_id).ok_or(NamespaceError::ParentMissing)?;
        if !parent.active { return Err(NamespaceError::Inactive); }
        let record = NamespaceRecord { id: id.clone(), path: path.clone(), parent: Some(parent_id), active: true };
        self.by_path.insert(path, id.clone());
        self.by_id.insert(id, record.clone());
        Ok(record)
    }

    pub fn resolve(&self, path: &NamespacePath) -> Result<&NamespaceRecord, NamespaceError> {
        let id = self.by_path.get(path).ok_or(NamespaceError::NotFound)?;
        let record = self.by_id.get(id).ok_or(NamespaceError::NotFound)?;
        if !record.active { return Err(NamespaceError::Inactive); }
        Ok(record)
    }

    pub fn get(&self, id: &NamespaceId) -> Result<&NamespaceRecord, NamespaceError> {
        let record = self.by_id.get(id).ok_or(NamespaceError::NotFound)?;
        if !record.active { return Err(NamespaceError::Inactive); }
        Ok(record)
    }

    pub fn disable(&mut self, id: &NamespaceId) -> Result<(), NamespaceError> {
        if id == &NamespaceId::root() { return Err(NamespaceError::RootImmutable); }
        let record = self.by_id.get_mut(id).ok_or(NamespaceError::NotFound)?;
        record.active = false;
        Ok(())
    }

    pub fn is_descendant_or_same(&self, child: &NamespaceId, ancestor: &NamespaceId) -> Result<bool, NamespaceError> {
        let mut current = self.get(child)?;
        loop {
            if current.id() == ancestor { return Ok(true); }
            let Some(parent_id) = current.parent() else { return Ok(false); };
            current = self.get(parent_id)?;
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn canonical_tree_and_disable_are_fail_closed() {
        let mut registry = NamespaceRegistry::default();
        let Ok(id) = NamespaceId::parse("team-a") else { assert!(false); return; };
        let Ok(path) = NamespacePath::parse("/team-a") else { assert!(false); return; };
        assert!(registry.create(id.clone(), path.clone()).is_ok());
        assert_eq!(registry.is_descendant_or_same(&id, &NamespaceId::root()), Ok(true));
        assert_eq!(registry.disable(&id), Ok(()));
        assert_eq!(registry.resolve(&path), Err(NamespaceError::Inactive));
        assert_eq!(NamespacePath::parse("/team-a/../root"), Err(NamespaceError::InvalidPath));
    }
}
'''


def policy_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use heptabao_namespace::NamespaceId;

#[derive(Clone, Copy, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum Capability { Create, Read, Update, Delete, List, Sudo }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RuleEffect { Allow, Deny }

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PolicyRule {
    namespace: Option<NamespaceId>,
    path_prefix: String,
    recursive: bool,
    capabilities: BTreeSet<Capability>,
    effect: RuleEffect,
}

impl PolicyRule {
    pub fn new(namespace: Option<NamespaceId>, path_prefix: &str, recursive: bool, capabilities: BTreeSet<Capability>, effect: RuleEffect) -> Result<Self, PolicyError> {
        if !path_prefix.starts_with('/') || path_prefix.contains("//") || capabilities.is_empty() {
            return Err(PolicyError::InvalidRule);
        }
        Ok(Self { namespace, path_prefix: path_prefix.to_owned(), recursive, capabilities, effect })
    }

    fn matches(&self, context: &PolicyContext) -> bool {
        if let Some(namespace) = &self.namespace {
            if namespace != &context.namespace { return false; }
        }
        if !self.capabilities.contains(&context.capability) { return false; }
        if context.resource == self.path_prefix { return true; }
        self.recursive && context.resource.strip_prefix(&self.path_prefix).is_some_and(|suffix| suffix.starts_with('/'))
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Policy { name: String, rules: Vec<PolicyRule> }

impl Policy {
    pub fn new(name: &str, rules: Vec<PolicyRule>) -> Result<Self, PolicyError> {
        if name.is_empty() || rules.is_empty() { return Err(PolicyError::InvalidPolicy); }
        Ok(Self { name: name.to_owned(), rules })
    }
    pub fn name(&self) -> &str { &self.name }
    pub fn rules(&self) -> &[PolicyRule] { &self.rules }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PolicyContext { pub namespace: NamespaceId, pub resource: String, pub capability: Capability }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum PolicyDecision { Allowed, DeniedExplicit, DeniedNoMatch }

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PolicyError { InvalidRule, InvalidPolicy, DuplicatePolicy, PolicyMissing }

#[derive(Clone, Debug, Default)]
pub struct PolicyStore { policies: BTreeMap<String, Policy> }

impl PolicyStore {
    pub fn insert(&mut self, policy: Policy) -> Result<(), PolicyError> {
        if self.policies.contains_key(policy.name()) { return Err(PolicyError::DuplicatePolicy); }
        self.policies.insert(policy.name().to_owned(), policy);
        Ok(())
    }
    pub fn get(&self, name: &str) -> Result<&Policy, PolicyError> { self.policies.get(name).ok_or(PolicyError::PolicyMissing) }
    pub fn evaluate_names(&self, names: &BTreeSet<String>, context: &PolicyContext) -> Result<PolicyDecision, PolicyError> {
        let mut allowed = false;
        for name in names {
            let policy = self.get(name)?;
            for rule in policy.rules() {
                if rule.matches(context) {
                    match rule.effect {
                        RuleEffect::Deny => return Ok(PolicyDecision::DeniedExplicit),
                        RuleEffect::Allow => allowed = true,
                    }
                }
            }
        }
        Ok(if allowed { PolicyDecision::Allowed } else { PolicyDecision::DeniedNoMatch })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn explicit_deny_wins_across_policy_union() {
        let mut read = BTreeSet::new(); read.insert(Capability::Read);
        let Ok(allow_rule) = PolicyRule::new(None, "/secret", true, read.clone(), RuleEffect::Allow) else { assert!(false); return; };
        let Ok(deny_rule) = PolicyRule::new(None, "/secret/admin", true, read, RuleEffect::Deny) else { assert!(false); return; };
        let Ok(allow) = Policy::new("allow", vec![allow_rule]) else { assert!(false); return; };
        let Ok(deny) = Policy::new("deny", vec![deny_rule]) else { assert!(false); return; };
        let mut store = PolicyStore::default();
        assert_eq!(store.insert(allow), Ok(())); assert_eq!(store.insert(deny), Ok(()));
        let names = BTreeSet::from(["allow".to_owned(), "deny".to_owned()]);
        let context = PolicyContext { namespace: NamespaceId::root(), resource: "/secret/admin/key".to_owned(), capability: Capability::Read };
        assert_eq!(store.evaluate_names(&names, &context), Ok(PolicyDecision::DeniedExplicit));
    }
}
'''


def identity_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};

fn valid_id(value: &str) -> bool {
    !value.is_empty() && value.len() <= 128 && value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_'))
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct EntityId(String);
impl EntityId {
    pub fn parse(value: &str) -> Result<Self, IdentityError> { if valid_id(value) { Ok(Self(value.to_owned())) } else { Err(IdentityError::InvalidId) } }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct GroupId(String);
impl GroupId {
    pub fn parse(value: &str) -> Result<Self, IdentityError> { if valid_id(value) { Ok(Self(value.to_owned())) } else { Err(IdentityError::InvalidId) } }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct EntityRecord { id: EntityId, policies: BTreeSet<String>, active: bool }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct GroupRecord { id: GroupId, policies: BTreeSet<String>, members: BTreeSet<EntityId>, active: bool }

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct IdentitySnapshot { entity: EntityId, groups: BTreeSet<GroupId>, policies: BTreeSet<String> }
impl IdentitySnapshot {
    pub fn entity(&self) -> &EntityId { &self.entity }
    pub fn groups(&self) -> &BTreeSet<GroupId> { &self.groups }
    pub fn policies(&self) -> &BTreeSet<String> { &self.policies }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum IdentityError { InvalidId, DuplicateEntity, DuplicateGroup, EntityMissing, GroupMissing, Inactive }

#[derive(Clone, Debug, Default)]
pub struct IdentityStore { entities: BTreeMap<EntityId, EntityRecord>, groups: BTreeMap<GroupId, GroupRecord> }

impl IdentityStore {
    pub fn create_entity(&mut self, id: EntityId, policies: BTreeSet<String>) -> Result<(), IdentityError> {
        if self.entities.contains_key(&id) { return Err(IdentityError::DuplicateEntity); }
        self.entities.insert(id.clone(), EntityRecord { id, policies, active: true }); Ok(())
    }
    pub fn create_group(&mut self, id: GroupId, policies: BTreeSet<String>) -> Result<(), IdentityError> {
        if self.groups.contains_key(&id) { return Err(IdentityError::DuplicateGroup); }
        self.groups.insert(id.clone(), GroupRecord { id, policies, members: BTreeSet::new(), active: true }); Ok(())
    }
    pub fn add_member(&mut self, group: &GroupId, entity: &EntityId) -> Result<(), IdentityError> {
        let record = self.entities.get(entity).ok_or(IdentityError::EntityMissing)?;
        if !record.active { return Err(IdentityError::Inactive); }
        let group_record = self.groups.get_mut(group).ok_or(IdentityError::GroupMissing)?;
        if !group_record.active { return Err(IdentityError::Inactive); }
        group_record.members.insert(entity.clone()); Ok(())
    }
    pub fn snapshot(&self, entity: &EntityId) -> Result<IdentitySnapshot, IdentityError> {
        let record = self.entities.get(entity).ok_or(IdentityError::EntityMissing)?;
        if !record.active { return Err(IdentityError::Inactive); }
        let mut groups = BTreeSet::new();
        let mut policies = record.policies.clone();
        for (id, group) in &self.groups {
            if group.active && group.members.contains(entity) {
                groups.insert(id.clone()); policies.extend(group.policies.iter().cloned());
            }
        }
        Ok(IdentitySnapshot { entity: record.id.clone(), groups, policies })
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn snapshot_unions_entity_and_group_policies() {
        let Ok(entity) = EntityId::parse("entity-a") else { assert!(false); return; };
        let Ok(group) = GroupId::parse("group-a") else { assert!(false); return; };
        let mut store = IdentityStore::default();
        assert_eq!(store.create_entity(entity.clone(), BTreeSet::from(["entity-policy".to_owned()])), Ok(()));
        assert_eq!(store.create_group(group.clone(), BTreeSet::from(["group-policy".to_owned()])), Ok(()));
        assert_eq!(store.add_member(&group, &entity), Ok(()));
        let Ok(snapshot) = store.snapshot(&entity) else { assert!(false); return; };
        assert!(snapshot.policies().contains("entity-policy")); assert!(snapshot.policies().contains("group-policy"));
    }
}
'''


def token_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use heptabao_identity::EntityId;
use heptabao_namespace::NamespaceId;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct TokenId(String);
impl TokenId {
    pub fn parse(value: &str) -> Result<Self, TokenError> {
        if value.len() < 8 || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')) { return Err(TokenError::InvalidId); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TokenIssue {
    pub id: TokenId,
    pub namespace: NamespaceId,
    pub entity: EntityId,
    pub policy_names: BTreeSet<String>,
    pub issued_at_ms: u64,
    pub ttl_ms: u64,
    pub use_limit: Option<u64>,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct TokenSnapshot {
    id: TokenId, namespace: NamespaceId, entity: EntityId, policy_names: BTreeSet<String>, expires_at_ms: u64, remaining_uses: Option<u64>,
}
impl TokenSnapshot {
    pub fn id(&self) -> &TokenId { &self.id }
    pub fn namespace(&self) -> &NamespaceId { &self.namespace }
    pub fn entity(&self) -> &EntityId { &self.entity }
    pub fn policy_names(&self) -> &BTreeSet<String> { &self.policy_names }
    pub fn expires_at_ms(&self) -> u64 { self.expires_at_ms }
    pub fn remaining_uses(&self) -> Option<u64> { self.remaining_uses }
}

#[derive(Clone, Debug)]
struct TokenRecord { snapshot: TokenSnapshot, revoked: bool }

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum TokenError { InvalidId, Duplicate, Missing, Expired, Revoked, NamespaceMismatch, UsesExhausted, InvalidTtl, ClockOverflow }

#[derive(Clone, Debug, Default)]
pub struct TokenStore { records: BTreeMap<TokenId, TokenRecord> }

impl TokenStore {
    pub fn issue(&mut self, issue: TokenIssue) -> Result<TokenSnapshot, TokenError> {
        if issue.ttl_ms == 0 { return Err(TokenError::InvalidTtl); }
        if self.records.contains_key(&issue.id) { return Err(TokenError::Duplicate); }
        let expires_at_ms = issue.issued_at_ms.checked_add(issue.ttl_ms).ok_or(TokenError::ClockOverflow)?;
        let snapshot = TokenSnapshot { id: issue.id.clone(), namespace: issue.namespace, entity: issue.entity, policy_names: issue.policy_names, expires_at_ms, remaining_uses: issue.use_limit };
        self.records.insert(issue.id, TokenRecord { snapshot: snapshot.clone(), revoked: false }); Ok(snapshot)
    }
    pub fn validate(&self, id: &TokenId, namespace: &NamespaceId, now_ms: u64) -> Result<TokenSnapshot, TokenError> {
        let record = self.records.get(id).ok_or(TokenError::Missing)?;
        if record.revoked { return Err(TokenError::Revoked); }
        if now_ms >= record.snapshot.expires_at_ms { return Err(TokenError::Expired); }
        if &record.snapshot.namespace != namespace { return Err(TokenError::NamespaceMismatch); }
        if record.snapshot.remaining_uses == Some(0) { return Err(TokenError::UsesExhausted); }
        Ok(record.snapshot.clone())
    }
    pub fn consume(&mut self, id: &TokenId, namespace: &NamespaceId, now_ms: u64) -> Result<TokenSnapshot, TokenError> {
        let snapshot = self.validate(id, namespace, now_ms)?;
        let record = self.records.get_mut(id).ok_or(TokenError::Missing)?;
        if let Some(remaining) = record.snapshot.remaining_uses {
            record.snapshot.remaining_uses = Some(remaining.checked_sub(1).ok_or(TokenError::UsesExhausted)?);
        }
        Ok(snapshot)
    }
    pub fn revoke(&mut self, id: &TokenId) -> Result<(), TokenError> {
        let record = self.records.get_mut(id).ok_or(TokenError::Missing)?; record.revoked = true; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn token_scope_ttl_use_and_revocation_fail_closed() {
        let Ok(id) = TokenId::parse("token-0001") else { assert!(false); return; };
        let Ok(entity) = EntityId::parse("entity-a") else { assert!(false); return; };
        let issue = TokenIssue { id: id.clone(), namespace: NamespaceId::root(), entity, policy_names: BTreeSet::new(), issued_at_ms: 10, ttl_ms: 100, use_limit: Some(1) };
        let mut store = TokenStore::default(); assert!(store.issue(issue).is_ok());
        assert!(store.consume(&id, &NamespaceId::root(), 20).is_ok());
        assert_eq!(store.consume(&id, &NamespaceId::root(), 21), Err(TokenError::UsesExhausted));
        assert_eq!(store.revoke(&id), Ok(())); assert_eq!(store.validate(&id, &NamespaceId::root(), 22), Err(TokenError::Revoked));
    }
}
'''


def lease_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use heptabao_namespace::NamespaceId;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct LeaseId(String);
impl LeaseId {
    pub fn parse(value: &str) -> Result<Self, LeaseError> {
        if value.len() < 8 || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')) { return Err(LeaseError::InvalidId); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct LeaseSnapshot { id: LeaseId, namespace: NamespaceId, expires_at_ms: u64, renewable: bool, revoked: bool }
impl LeaseSnapshot {
    pub fn id(&self) -> &LeaseId { &self.id }
    pub fn namespace(&self) -> &NamespaceId { &self.namespace }
    pub fn expires_at_ms(&self) -> u64 { self.expires_at_ms }
    pub fn is_renewable(&self) -> bool { self.renewable }
    pub fn is_revoked(&self) -> bool { self.revoked }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum LeaseError { InvalidId, Duplicate, Missing, Expired, Revoked, NotRenewable, InvalidTtl, ClockOverflow }

#[derive(Clone, Debug, Default)]
pub struct LeaseStore { leases: BTreeMap<LeaseId, LeaseSnapshot> }
impl LeaseStore {
    pub fn issue(&mut self, id: LeaseId, namespace: NamespaceId, now_ms: u64, ttl_ms: u64, renewable: bool) -> Result<LeaseSnapshot, LeaseError> {
        if ttl_ms == 0 { return Err(LeaseError::InvalidTtl); }
        if self.leases.contains_key(&id) { return Err(LeaseError::Duplicate); }
        let expires_at_ms = now_ms.checked_add(ttl_ms).ok_or(LeaseError::ClockOverflow)?;
        let lease = LeaseSnapshot { id: id.clone(), namespace, expires_at_ms, renewable, revoked: false };
        self.leases.insert(id, lease.clone()); Ok(lease)
    }
    pub fn inspect(&self, id: &LeaseId, now_ms: u64) -> Result<&LeaseSnapshot, LeaseError> {
        let lease = self.leases.get(id).ok_or(LeaseError::Missing)?;
        if lease.revoked { return Err(LeaseError::Revoked); }
        if now_ms >= lease.expires_at_ms { return Err(LeaseError::Expired); }
        Ok(lease)
    }
    pub fn renew(&mut self, id: &LeaseId, now_ms: u64, ttl_ms: u64) -> Result<LeaseSnapshot, LeaseError> {
        let current = self.inspect(id, now_ms)?.clone();
        if !current.renewable { return Err(LeaseError::NotRenewable); }
        if ttl_ms == 0 { return Err(LeaseError::InvalidTtl); }
        let expires_at_ms = now_ms.checked_add(ttl_ms).ok_or(LeaseError::ClockOverflow)?;
        let lease = self.leases.get_mut(id).ok_or(LeaseError::Missing)?; lease.expires_at_ms = expires_at_ms; Ok(lease.clone())
    }
    pub fn revoke(&mut self, id: &LeaseId) -> Result<(), LeaseError> {
        let lease = self.leases.get_mut(id).ok_or(LeaseError::Missing)?; lease.revoked = true; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn renewal_and_revocation_are_explicit() {
        let Ok(id) = LeaseId::parse("lease-0001") else { assert!(false); return; };
        let mut store = LeaseStore::default(); assert!(store.issue(id.clone(), NamespaceId::root(), 10, 50, true).is_ok());
        assert!(store.renew(&id, 20, 80).is_ok()); assert_eq!(store.revoke(&id), Ok(())); assert_eq!(store.inspect(&id, 21), Err(LeaseError::Revoked));
    }
}
'''


def system_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use heptabao_namespace::NamespaceId;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct MountId(String);
impl MountId {
    pub fn parse(value: &str) -> Result<Self, MountError> {
        if value.is_empty() || value.len() > 64 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')) { return Err(MountError::InvalidId); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MountKind { Kv, System, Plugin { plugin_id: String } }

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct MountEntry { id: MountId, namespace: NamespaceId, path: String, kind: MountKind, active: bool }
impl MountEntry {
    pub fn new(id: MountId, namespace: NamespaceId, path: &str, kind: MountKind) -> Result<Self, MountError> {
        if !path.starts_with('/') || path == "/" || path.ends_with('/') || path.contains("//") { return Err(MountError::InvalidPath); }
        Ok(Self { id, namespace, path: path.to_owned(), kind, active: true })
    }
    pub fn id(&self) -> &MountId { &self.id }
    pub fn namespace(&self) -> &NamespaceId { &self.namespace }
    pub fn path(&self) -> &str { &self.path }
    pub fn kind(&self) -> &MountKind { &self.kind }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum MountError { InvalidId, InvalidPath, Duplicate, Missing, Inactive }

#[derive(Clone, Debug, Default)]
pub struct MountTable { entries: BTreeMap<(NamespaceId, String), MountEntry> }
impl MountTable {
    pub fn mount(&mut self, entry: MountEntry) -> Result<(), MountError> {
        let key = (entry.namespace.clone(), entry.path.clone());
        if self.entries.contains_key(&key) { return Err(MountError::Duplicate); }
        self.entries.insert(key, entry); Ok(())
    }
    pub fn resolve(&self, namespace: &NamespaceId, request_path: &str) -> Result<&MountEntry, MountError> {
        let mut selected: Option<&MountEntry> = None;
        for ((candidate_namespace, _), entry) in &self.entries {
            if candidate_namespace != namespace || !entry.active { continue; }
            let matches = request_path == entry.path || request_path.strip_prefix(&entry.path).is_some_and(|suffix| suffix.starts_with('/'));
            if matches && selected.is_none_or(|current| entry.path.len() > current.path.len()) { selected = Some(entry); }
        }
        selected.ok_or(MountError::Missing)
    }
    pub fn disable(&mut self, namespace: &NamespaceId, path: &str) -> Result<(), MountError> {
        let entry = self.entries.get_mut(&(namespace.clone(), path.to_owned())).ok_or(MountError::Missing)?; entry.active = false; Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn longest_prefix_resolves_without_fallback() {
        let Ok(root_id) = MountId::parse("root-kv") else { assert!(false); return; };
        let Ok(admin_id) = MountId::parse("admin-kv") else { assert!(false); return; };
        let Ok(root) = MountEntry::new(root_id, NamespaceId::root(), "/secret", MountKind::Kv) else { assert!(false); return; };
        let Ok(admin) = MountEntry::new(admin_id, NamespaceId::root(), "/secret/admin", MountKind::System) else { assert!(false); return; };
        let mut table = MountTable::default(); assert_eq!(table.mount(root), Ok(())); assert_eq!(table.mount(admin), Ok(()));
        let Ok(resolved) = table.resolve(&NamespaceId::root(), "/secret/admin/x") else { assert!(false); return; };
        assert!(matches!(resolved.kind(), MountKind::System)); assert_eq!(table.resolve(&NamespaceId::root(), "/missing/x"), Err(MountError::Missing));
    }
}
'''


def plugin_contracts_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::BTreeSet;

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct PluginId(String);
impl PluginId {
    pub fn parse(value: &str) -> Result<Self, PluginContractError> {
        if value.is_empty() || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.')) { return Err(PluginContractError::InvalidId); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginDigest(String);
impl PluginDigest {
    pub fn parse(value: &str) -> Result<Self, PluginContractError> {
        let Some(hex) = value.strip_prefix("sha256:") else { return Err(PluginContractError::InvalidDigest); };
        if hex.len() != 64 || !hex.bytes().all(|byte| byte.is_ascii_hexdigit() && !byte.is_ascii_uppercase()) { return Err(PluginContractError::InvalidDigest); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
pub enum PluginCapability { ReadRequest, WriteResponse, ExternalNetwork, PersistentState }

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct PluginDescriptor { id: PluginId, digest: PluginDigest, protocol_version: u32, capabilities: BTreeSet<PluginCapability> }
impl PluginDescriptor {
    pub fn new(id: PluginId, digest: PluginDigest, protocol_version: u32, capabilities: BTreeSet<PluginCapability>) -> Result<Self, PluginContractError> {
        if protocol_version == 0 { return Err(PluginContractError::InvalidProtocol); }
        Ok(Self { id, digest, protocol_version, capabilities })
    }
    pub fn id(&self) -> &PluginId { &self.id }
    pub fn digest(&self) -> &PluginDigest { &self.digest }
    pub fn protocol_version(&self) -> u32 { self.protocol_version }
    pub fn capabilities(&self) -> &BTreeSet<PluginCapability> { &self.capabilities }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum PluginContractError { InvalidId, InvalidDigest, InvalidProtocol }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn descriptor_requires_exact_lowercase_digest() {
        let Ok(id) = PluginId::parse("kv.plugin") else { assert!(false); return; };
        let Ok(digest) = PluginDigest::parse(&format!("sha256:{}", "a".repeat(64))) else { assert!(false); return; };
        assert!(PluginDescriptor::new(id, digest, 1, BTreeSet::new()).is_ok());
        assert_eq!(PluginDigest::parse(&format!("sha256:{}", "A".repeat(64))), Err(PluginContractError::InvalidDigest));
    }
}
'''


def kv_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use heptabao_namespace::NamespaceId;
use heptabao_system::MountId;

#[derive(Clone, Eq, PartialEq)]
pub struct SecretBytes(Vec<u8>);
impl SecretBytes {
    pub fn new(value: Vec<u8>) -> Result<Self, KvError> { if value.is_empty() { Err(KvError::EmptyValue) } else { Ok(Self(value)) } }
    pub fn expose(&self) -> &[u8] { &self.0 }
    pub fn len(&self) -> usize { self.0.len() }
    pub fn is_empty(&self) -> bool { self.0.is_empty() }
}
impl fmt::Debug for SecretBytes {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { formatter.debug_struct("SecretBytes").field("len", &self.0.len()).finish_non_exhaustive() }
}

#[derive(Clone, Debug, Eq, Ord, PartialEq, PartialOrd)]
struct KvKey { namespace: NamespaceId, mount: MountId, path: String }

#[derive(Clone, Eq, PartialEq)]
pub struct KvVersion { version: u64, value: Option<SecretBytes>, deleted: bool, destroyed: bool, created_at_ms: u64 }
impl fmt::Debug for KvVersion {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter.debug_struct("KvVersion").field("version", &self.version).field("value_len", &self.value.as_ref().map(SecretBytes::len)).field("deleted", &self.deleted).field("destroyed", &self.destroyed).field("created_at_ms", &self.created_at_ms).finish()
    }
}
impl KvVersion {
    pub fn version(&self) -> u64 { self.version }
    pub fn value(&self) -> Option<&SecretBytes> { self.value.as_ref() }
    pub fn is_deleted(&self) -> bool { self.deleted }
    pub fn is_destroyed(&self) -> bool { self.destroyed }
    pub fn created_at_ms(&self) -> u64 { self.created_at_ms }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum KvError { InvalidPath, EmptyValue, CasMismatch, VersionMissing, Deleted, Destroyed, VersionOverflow, VersionLimit, DuplicateVersionRequest }

#[derive(Clone, Debug)]
pub struct KvStore { entries: BTreeMap<KvKey, Vec<KvVersion>>, max_versions: usize }
impl KvStore {
    pub fn new(max_versions: usize) -> Result<Self, KvError> { if max_versions == 0 { Err(KvError::VersionLimit) } else { Ok(Self { entries: BTreeMap::new(), max_versions }) } }
    fn key(namespace: &NamespaceId, mount: &MountId, path: &str) -> Result<KvKey, KvError> {
        if !path.starts_with('/') || path.contains("//") || path.ends_with('/') { return Err(KvError::InvalidPath); }
        Ok(KvKey { namespace: namespace.clone(), mount: mount.clone(), path: path.to_owned() })
    }
    pub fn put(&mut self, namespace: &NamespaceId, mount: &MountId, path: &str, value: SecretBytes, cas: Option<u64>, now_ms: u64) -> Result<KvVersion, KvError> {
        let key = Self::key(namespace, mount, path)?;
        let versions = self.entries.entry(key).or_default();
        let current = versions.last().map_or(0, |entry| entry.version);
        if cas.is_some_and(|expected| expected != current) { return Err(KvError::CasMismatch); }
        if versions.len() >= self.max_versions { return Err(KvError::VersionLimit); }
        let version = current.checked_add(1).ok_or(KvError::VersionOverflow)?;
        let entry = KvVersion { version, value: Some(value), deleted: false, destroyed: false, created_at_ms: now_ms };
        versions.push(entry.clone()); Ok(entry)
    }
    pub fn read(&self, namespace: &NamespaceId, mount: &MountId, path: &str, version: Option<u64>) -> Result<KvVersion, KvError> {
        let key = Self::key(namespace, mount, path)?;
        let versions = self.entries.get(&key).ok_or(KvError::VersionMissing)?;
        let entry = if let Some(version) = version { versions.iter().find(|entry| entry.version == version) } else { versions.last() }.ok_or(KvError::VersionMissing)?;
        if entry.destroyed { return Err(KvError::Destroyed); }
        if entry.deleted { return Err(KvError::Deleted); }
        Ok(entry.clone())
    }
    fn validate_versions(versions: &[KvVersion], requested: &[u64]) -> Result<BTreeSet<u64>, KvError> {
        let set: BTreeSet<u64> = requested.iter().copied().collect();
        if set.len() != requested.len() { return Err(KvError::DuplicateVersionRequest); }
        if set.iter().any(|version| !versions.iter().any(|entry| entry.version == *version)) { return Err(KvError::VersionMissing); }
        Ok(set)
    }
    pub fn delete_versions(&mut self, namespace: &NamespaceId, mount: &MountId, path: &str, requested: &[u64]) -> Result<(), KvError> {
        let key = Self::key(namespace, mount, path)?;
        let versions = self.entries.get_mut(&key).ok_or(KvError::VersionMissing)?;
        let selected = Self::validate_versions(versions, requested)?;
        for entry in versions { if selected.contains(&entry.version) { if entry.destroyed { return Err(KvError::Destroyed); } entry.deleted = true; } }
        Ok(())
    }
    pub fn undelete_versions(&mut self, namespace: &NamespaceId, mount: &MountId, path: &str, requested: &[u64]) -> Result<(), KvError> {
        let key = Self::key(namespace, mount, path)?;
        let versions = self.entries.get_mut(&key).ok_or(KvError::VersionMissing)?;
        let selected = Self::validate_versions(versions, requested)?;
        if versions.iter().any(|entry| selected.contains(&entry.version) && entry.destroyed) { return Err(KvError::Destroyed); }
        for entry in versions { if selected.contains(&entry.version) { entry.deleted = false; } }
        Ok(())
    }
    pub fn destroy_versions(&mut self, namespace: &NamespaceId, mount: &MountId, path: &str, requested: &[u64]) -> Result<(), KvError> {
        let key = Self::key(namespace, mount, path)?;
        let versions = self.entries.get_mut(&key).ok_or(KvError::VersionMissing)?;
        let selected = Self::validate_versions(versions, requested)?;
        for entry in versions { if selected.contains(&entry.version) { entry.value = None; entry.deleted = true; entry.destroyed = true; } }
        Ok(())
    }
    pub fn list(&self, namespace: &NamespaceId, mount: &MountId, prefix: &str) -> Result<Vec<String>, KvError> {
        if !prefix.starts_with('/') { return Err(KvError::InvalidPath); }
        Ok(self.entries.keys().filter(|key| &key.namespace == namespace && &key.mount == mount && key.path.starts_with(prefix)).map(|key| key.path.clone()).collect())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn versions_cas_and_destroy_are_fail_closed() {
        let Ok(mount) = MountId::parse("kv-main") else { assert!(false); return; };
        let Ok(mut store) = KvStore::new(4) else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"secret".to_vec()) else { assert!(false); return; };
        let Ok(first) = store.put(&NamespaceId::root(), &mount, "/a", value, Some(0), 10) else { assert!(false); return; };
        assert_eq!(first.version(), 1);
        let Ok(other) = SecretBytes::new(b"other".to_vec()) else { assert!(false); return; };
        assert_eq!(store.put(&NamespaceId::root(), &mount, "/a", other, Some(0), 11), Err(KvError::CasMismatch));
        assert_eq!(store.destroy_versions(&NamespaceId::root(), &mount, "/a", &[1]), Ok(()));
        assert_eq!(store.read(&NamespaceId::root(), &mount, "/a", Some(1)), Err(KvError::Destroyed));
    }
}
'''


def control_plane_rs() -> str:
    return r'''#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::fmt;
use heptabao_identity::{EntityId, IdentityError, IdentityStore};
use heptabao_kv::{KvError, KvStore, KvVersion, SecretBytes};
use heptabao_namespace::{NamespaceError, NamespaceId, NamespaceRegistry};
use heptabao_policy::{Capability, PolicyContext, PolicyDecision, PolicyError, PolicyStore};
use heptabao_system::{MountError, MountId, MountKind, MountTable};
use heptabao_token::{TokenError, TokenId, TokenStore};

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct RequestId(String);
impl RequestId {
    pub fn parse(value: &str) -> Result<Self, ControlPlaneError> {
        if value.len() < 8 || value.len() > 128 || !value.bytes().all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_')) { return Err(ControlPlaneError::InvalidRequest); }
        Ok(Self(value.to_owned()))
    }
    pub fn as_str(&self) -> &str { &self.0 }
}

#[derive(Clone, Eq, PartialEq)]
pub enum Operation {
    Read { path: String, version: Option<u64> },
    Put { path: String, value: SecretBytes, cas: Option<u64> },
    Delete { path: String, versions: Vec<u64> },
    Undelete { path: String, versions: Vec<u64> },
    Destroy { path: String, versions: Vec<u64> },
    List { prefix: String },
}
impl fmt::Debug for Operation {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Read { path, version } => formatter.debug_struct("Read").field("path", path).field("version", version).finish(),
            Self::Put { path, value, cas } => formatter.debug_struct("Put").field("path", path).field("value_len", &value.len()).field("cas", cas).finish(),
            Self::Delete { path, versions } => formatter.debug_struct("Delete").field("path", path).field("versions", versions).finish(),
            Self::Undelete { path, versions } => formatter.debug_struct("Undelete").field("path", path).field("versions", versions).finish(),
            Self::Destroy { path, versions } => formatter.debug_struct("Destroy").field("path", path).field("versions", versions).finish(),
            Self::List { prefix } => formatter.debug_struct("List").field("prefix", prefix).finish(),
        }
    }
}
impl Operation {
    fn path(&self) -> &str { match self { Self::Read { path, .. } | Self::Put { path, .. } | Self::Delete { path, .. } | Self::Undelete { path, .. } | Self::Destroy { path, .. } => path, Self::List { prefix } => prefix } }
    fn capability(&self) -> Capability { match self { Self::Read { .. } => Capability::Read, Self::Put { cas: Some(0), .. } => Capability::Create, Self::Put { .. } => Capability::Update, Self::Delete { .. } | Self::Undelete { .. } | Self::Destroy { .. } => Capability::Delete, Self::List { .. } => Capability::List } }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Request { pub id: RequestId, pub namespace: NamespaceId, pub token: TokenId, pub now_ms: u64, pub operation: Operation }

#[derive(Clone, Eq, PartialEq)]
pub enum Response { Version(KvVersion), Keys(Vec<String>), Empty }
impl fmt::Debug for Response {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result { match self { Self::Version(value) => formatter.debug_tuple("Version").field(value).finish(), Self::Keys(keys) => formatter.debug_tuple("Keys").field(keys).finish(), Self::Empty => formatter.write_str("Empty") } }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditPhase { Intent, Outcome }
#[derive(Clone, Debug, Eq, PartialEq)]
pub struct AuditEvent { pub phase: AuditPhase, pub request_id: RequestId, pub namespace: NamespaceId, pub resource: String, pub capability: Capability, pub success: Option<bool> }
#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum AuditFailure { BeforeRecord, OutcomeUnknownAfterEntry }
pub trait AuditSink { fn record_intent(&mut self, event: AuditEvent) -> Result<(), AuditFailure>; fn record_outcome(&mut self, event: AuditEvent) -> Result<(), AuditFailure>; }

#[derive(Clone, Debug, Default)]
pub struct MemoryAuditSink { events: Vec<AuditEvent>, fail_intent_once: bool, fail_outcome_once: bool }
impl MemoryAuditSink {
    pub fn events(&self) -> &[AuditEvent] { &self.events }
    pub fn fail_next_intent(&mut self) { self.fail_intent_once = true; }
    pub fn fail_next_outcome(&mut self) { self.fail_outcome_once = true; }
}
impl AuditSink for MemoryAuditSink {
    fn record_intent(&mut self, event: AuditEvent) -> Result<(), AuditFailure> { if self.fail_intent_once { self.fail_intent_once = false; return Err(AuditFailure::BeforeRecord); } self.events.push(event); Ok(()) }
    fn record_outcome(&mut self, event: AuditEvent) -> Result<(), AuditFailure> { if self.fail_outcome_once { self.fail_outcome_once = false; return Err(AuditFailure::OutcomeUnknownAfterEntry); } self.events.push(event); Ok(()) }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ControlPlaneError {
    InvalidRequest, RequestIdConflict, RequestInProgress, OutcomeUnknown,
    Namespace(NamespaceError), Token(TokenError), Identity(IdentityError), Policy(PolicyError), Denied(PolicyDecision), Mount(MountError), UnsupportedMount, Kv(KvError), AuditBeforeIntent, AuditOutcomeUnknown,
}
impl From<NamespaceError> for ControlPlaneError { fn from(value: NamespaceError) -> Self { Self::Namespace(value) } }
impl From<TokenError> for ControlPlaneError { fn from(value: TokenError) -> Self { Self::Token(value) } }
impl From<IdentityError> for ControlPlaneError { fn from(value: IdentityError) -> Self { Self::Identity(value) } }
impl From<PolicyError> for ControlPlaneError { fn from(value: PolicyError) -> Self { Self::Policy(value) } }
impl From<MountError> for ControlPlaneError { fn from(value: MountError) -> Self { Self::Mount(value) } }
impl From<KvError> for ControlPlaneError { fn from(value: KvError) -> Self { Self::Kv(value) } }

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
struct RequestDigest(u64);
#[derive(Clone, Debug)]
enum LedgerState { InProgress(RequestDigest), OutcomeUnknown(RequestDigest, Response), Completed(RequestDigest, Response) }

pub struct ControlPlane<A: AuditSink> {
    pub namespaces: NamespaceRegistry,
    pub identities: IdentityStore,
    pub policies: PolicyStore,
    pub tokens: TokenStore,
    pub mounts: MountTable,
    pub kv: KvStore,
    pub audit: A,
    ledger: BTreeMap<RequestId, LedgerState>,
}

impl<A: AuditSink> ControlPlane<A> {
    pub fn new(namespaces: NamespaceRegistry, identities: IdentityStore, policies: PolicyStore, tokens: TokenStore, mounts: MountTable, kv: KvStore, audit: A) -> Self {
        Self { namespaces, identities, policies, tokens, mounts, kv, audit, ledger: BTreeMap::new() }
    }

    pub fn execute(&mut self, request: Request) -> Result<Response, ControlPlaneError> {
        let digest = request_digest(&request);
        if let Some(state) = self.ledger.get(&request.id).cloned() {
            return match state {
                LedgerState::Completed(existing, response) if existing == digest => Ok(response),
                LedgerState::OutcomeUnknown(existing, _) if existing == digest => Err(ControlPlaneError::OutcomeUnknown),
                LedgerState::InProgress(existing) if existing == digest => Err(ControlPlaneError::RequestInProgress),
                LedgerState::Completed(_, _) | LedgerState::OutcomeUnknown(_, _) | LedgerState::InProgress(_) => Err(ControlPlaneError::RequestIdConflict),
            };
        }
        self.namespaces.get(&request.namespace)?;
        let token = self.tokens.validate(&request.token, &request.namespace, request.now_ms)?;
        let identity = self.identities.snapshot(token.entity())?;
        let mut policy_names: BTreeSet<String> = token.policy_names().clone();
        policy_names.extend(identity.policies().iter().cloned());
        let mount = self.mounts.resolve(&request.namespace, request.operation.path())?.clone();
        if !matches!(mount.kind(), MountKind::Kv) { return Err(ControlPlaneError::UnsupportedMount); }
        let context = PolicyContext { namespace: request.namespace.clone(), resource: request.operation.path().to_owned(), capability: request.operation.capability() };
        let decision = self.policies.evaluate_names(&policy_names, &context)?;
        if decision != PolicyDecision::Allowed { return Err(ControlPlaneError::Denied(decision)); }
        let intent = AuditEvent { phase: AuditPhase::Intent, request_id: request.id.clone(), namespace: request.namespace.clone(), resource: context.resource.clone(), capability: context.capability, success: None };
        self.audit.record_intent(intent).map_err(|_| ControlPlaneError::AuditBeforeIntent)?;
        self.ledger.insert(request.id.clone(), LedgerState::InProgress(digest));
        if let Err(error) = self.tokens.consume(&request.token, &request.namespace, request.now_ms) {
            self.ledger.remove(&request.id); return Err(ControlPlaneError::Token(error));
        }
        let effect = self.apply(&request.namespace, mount.id(), &request.operation, request.now_ms);
        let response = match effect {
            Ok(value) => value,
            Err(error) => {
                let outcome = AuditEvent { phase: AuditPhase::Outcome, request_id: request.id.clone(), namespace: request.namespace.clone(), resource: context.resource, capability: context.capability, success: Some(false) };
                if self.audit.record_outcome(outcome).is_err() { self.ledger.insert(request.id, LedgerState::InProgress(digest)); return Err(ControlPlaneError::AuditOutcomeUnknown); }
                self.ledger.remove(&request.id); return Err(ControlPlaneError::Kv(error));
            }
        };
        let outcome = AuditEvent { phase: AuditPhase::Outcome, request_id: request.id.clone(), namespace: request.namespace, resource: context.resource, capability: context.capability, success: Some(true) };
        if self.audit.record_outcome(outcome).is_err() {
            self.ledger.insert(request.id, LedgerState::OutcomeUnknown(digest, response)); return Err(ControlPlaneError::AuditOutcomeUnknown);
        }
        self.ledger.insert(request.id, LedgerState::Completed(digest, response.clone())); Ok(response)
    }

    pub fn confirm_outcome(&mut self, request_id: &RequestId) -> Result<Response, ControlPlaneError> {
        let state = self.ledger.get(request_id).cloned().ok_or(ControlPlaneError::InvalidRequest)?;
        let LedgerState::OutcomeUnknown(digest, response) = state else { return Err(ControlPlaneError::InvalidRequest); };
        self.ledger.insert(request_id.clone(), LedgerState::Completed(digest, response.clone())); Ok(response)
    }

    fn apply(&mut self, namespace: &NamespaceId, mount: &MountId, operation: &Operation, now_ms: u64) -> Result<Response, KvError> {
        match operation {
            Operation::Read { path, version } => self.kv.read(namespace, mount, relative_path(path, mount)?, *version).map(Response::Version),
            Operation::Put { path, value, cas } => self.kv.put(namespace, mount, relative_path(path, mount)?, value.clone(), *cas, now_ms).map(Response::Version),
            Operation::Delete { path, versions } => { self.kv.delete_versions(namespace, mount, relative_path(path, mount)?, versions)?; Ok(Response::Empty) }
            Operation::Undelete { path, versions } => { self.kv.undelete_versions(namespace, mount, relative_path(path, mount)?, versions)?; Ok(Response::Empty) }
            Operation::Destroy { path, versions } => { self.kv.destroy_versions(namespace, mount, relative_path(path, mount)?, versions)?; Ok(Response::Empty) }
            Operation::List { prefix } => self.kv.list(namespace, mount, relative_path(prefix, mount)?).map(Response::Keys),
        }
    }
}

fn relative_path<'a>(path: &'a str, _mount: &MountId) -> Result<&'a str, KvError> { if path.starts_with('/') { Ok(path) } else { Err(KvError::InvalidPath) } }

fn request_digest(request: &Request) -> RequestDigest {
    let mut hash = 0xcbf2_9ce4_8422_2325_u64;
    fn feed(hash: &mut u64, bytes: &[u8]) { for byte in bytes { *hash ^= u64::from(*byte); *hash = hash.wrapping_mul(0x0000_0100_0000_01b3); } }
    feed(&mut hash, request.id.as_str().as_bytes()); feed(&mut hash, request.namespace.as_str().as_bytes()); feed(&mut hash, request.token.as_str().as_bytes()); feed(&mut hash, &request.now_ms.to_be_bytes());
    match &request.operation {
        Operation::Read { path, version } => { feed(&mut hash, b"read"); feed(&mut hash, path.as_bytes()); feed(&mut hash, &version.unwrap_or(0).to_be_bytes()); }
        Operation::Put { path, value, cas } => { feed(&mut hash, b"put"); feed(&mut hash, path.as_bytes()); feed(&mut hash, value.expose()); feed(&mut hash, &cas.unwrap_or(u64::MAX).to_be_bytes()); }
        Operation::Delete { path, versions } | Operation::Undelete { path, versions } | Operation::Destroy { path, versions } => { feed(&mut hash, path.as_bytes()); for version in versions { feed(&mut hash, &version.to_be_bytes()); } }
        Operation::List { prefix } => { feed(&mut hash, b"list"); feed(&mut hash, prefix.as_bytes()); }
    }
    RequestDigest(hash)
}

#[cfg(test)]
mod tests {
    use super::*;
    use heptabao_identity::EntityId;
    use heptabao_policy::{Policy, PolicyRule, RuleEffect};
    use heptabao_system::{MountEntry, MountKind};
    use heptabao_token::TokenIssue;

    fn setup() -> Option<(ControlPlane<MemoryAuditSink>, TokenId)> {
        let namespace = NamespaceRegistry::default();
        let entity = EntityId::parse("entity-a").ok()?;
        let mut identities = IdentityStore::default(); identities.create_entity(entity.clone(), BTreeSet::new()).ok()?;
        let mut capabilities = BTreeSet::new(); capabilities.extend([Capability::Create, Capability::Read, Capability::Update, Capability::Delete, Capability::List]);
        let rule = PolicyRule::new(None, "/secret", true, capabilities, RuleEffect::Allow).ok()?;
        let policy = Policy::new("kv-access", vec![rule]).ok()?;
        let mut policies = PolicyStore::default(); policies.insert(policy).ok()?;
        let token_id = TokenId::parse("token-0001").ok()?;
        let mut tokens = TokenStore::default();
        tokens.issue(TokenIssue { id: token_id.clone(), namespace: NamespaceId::root(), entity, policy_names: BTreeSet::from(["kv-access".to_owned()]), issued_at_ms: 0, ttl_ms: 10_000, use_limit: Some(10) }).ok()?;
        let mount_id = MountId::parse("kv-main").ok()?;
        let mount = MountEntry::new(mount_id, NamespaceId::root(), "/secret", MountKind::Kv).ok()?;
        let mut mounts = MountTable::default(); mounts.mount(mount).ok()?;
        let kv = KvStore::new(10).ok()?;
        Some((ControlPlane::new(namespace, identities, policies, tokens, mounts, kv, MemoryAuditSink::default()), token_id))
    }

    #[test]
    fn completed_request_is_idempotent_and_conflicting_descriptor_is_rejected() {
        let Some((mut plane, token)) = setup() else { assert!(false); return; };
        let Ok(id) = RequestId::parse("request-0001") else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"one".to_vec()) else { assert!(false); return; };
        let request = Request { id: id.clone(), namespace: NamespaceId::root(), token: token.clone(), now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value, cas: Some(0) } };
        let first = plane.execute(request.clone()); let second = plane.execute(request);
        assert_eq!(first, second); assert_eq!(plane.audit.events().len(), 2);
        let Ok(other) = SecretBytes::new(b"two".to_vec()) else { assert!(false); return; };
        let conflict = Request { id, namespace: NamespaceId::root(), token, now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value: other, cas: Some(1) } };
        assert_eq!(plane.execute(conflict), Err(ControlPlaneError::RequestIdConflict));
    }

    #[test]
    fn post_effect_audit_failure_blocks_retry_until_reconciliation() {
        let Some((mut plane, token)) = setup() else { assert!(false); return; };
        plane.audit.fail_next_outcome();
        let Ok(id) = RequestId::parse("request-0002") else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"one".to_vec()) else { assert!(false); return; };
        let request = Request { id: id.clone(), namespace: NamespaceId::root(), token, now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value, cas: Some(0) } };
        assert_eq!(plane.execute(request.clone()), Err(ControlPlaneError::AuditOutcomeUnknown));
        assert_eq!(plane.execute(request), Err(ControlPlaneError::OutcomeUnknown));
        assert!(plane.confirm_outcome(&id).is_ok());
    }

    #[test]
    fn audit_intent_failure_has_no_kv_effect() {
        let Some((mut plane, token)) = setup() else { assert!(false); return; };
        plane.audit.fail_next_intent();
        let Ok(id) = RequestId::parse("request-0003") else { assert!(false); return; };
        let Ok(value) = SecretBytes::new(b"one".to_vec()) else { assert!(false); return; };
        let request = Request { id, namespace: NamespaceId::root(), token, now_ms: 10, operation: Operation::Put { path: "/secret/a".to_owned(), value, cas: Some(0) } };
        assert_eq!(plane.execute(request), Err(ControlPlaneError::AuditBeforeIntent));
        let Ok(mount) = MountId::parse("kv-main") else { assert!(false); return; };
        assert_eq!(plane.kv.read(&NamespaceId::root(), &mount, "/secret/a", None), Err(KvError::VersionMissing));
    }
}
'''


def module_doc(name: str, purpose: str, maturity: str, dependencies: str, invariants: list[str], gaps: list[str]) -> str:
    invariant_lines = "\n".join(f"- {item}" for item in invariants)
    gap_lines = "\n".join(f"- {item}" for item in gaps)
    return f'''# `{name}` developer guide

## Purpose and responsibility

{purpose}

## Maturity and authority

{maturity} Source implementation and tests do not establish production qualification, OpenBao compatibility, provider selection or authority.

## Dependency direction

{dependencies}

## Public API

Generated from exact source by the current Module Documentation V2 renderer.

## State model and invariants

{invariant_lines}

## Errors, failure classes, and retry semantics

Validation and authorization failures occur before effects and may be retried only after correcting input. Any explicitly outcome-unknown result requires reconciliation and must not be blindly retried.

## Data formats and compatibility

All identifiers and request structures are internal V1.5 contracts. No wire-format, storage-format or upstream compatibility promise is made.

## Security considerations

Inputs are canonicalized and fail closed. Secret payloads must not appear in Debug output, audit metadata or authority receipts. Namespace and request identity are never inferred from an untrusted path after authorization.

## Testing strategy

Unit tests cover positive state transitions, invalid identifiers, authorization boundaries, duplicate operations, retry classification and destructive operations where applicable. Workspace CI runs the exact-head and prospective-merge matrices.

## Extension rules

Add behavior through typed variants and explicit state transitions. Do not introduce fallback routing, ambient namespace inheritance, implicit allow, blind retry or unversioned destructive mutation.

## Operational guidance

This crate is not independently deployable. Operators must use it only through a reviewed composition root with durable audit, storage, recovery and revocation providers.

## Known gaps

{gap_lines}

## Traceability

- Plan: `docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md`
- Status: `planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml`
- Blockers: `planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml`
- Module truth: `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml`
'''


def module_renderer_source() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import subprocess
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TRUTH_PATH = Path("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml")
PLAN_ID = "HEPTABAO-PLAN-2026-09-02-V1.5.0"
SPEC = importlib.util.spec_from_file_location("v147_renderer", ROOT / "scripts/render_plan_v1_4_7.py")
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
BASE.PLAN_ID = PLAN_ID
BASE.TRUTH_PATH = TRUTH_PATH


def source_baseline(root: Path) -> dict[str, str]:
    value = yaml.safe_load((root / "planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml").read_text(encoding="utf-8"))
    return value["source_baseline"]


def truth(root: Path) -> dict:
    value = BASE.build_truth(root)
    value["schema"] = "heptabao.module-source-truth.v2"
    value["plan_id"] = PLAN_ID
    value.pop("baseline_commit", None)
    value.pop("baseline_tree", None)
    value["source_baseline"] = source_baseline(root)
    return value


def index_expected(root: Path, value: dict) -> str:
    path = root / "docs/modules/README.md"
    text = path.read_text(encoding="utf-8")
    for begin, end in ((BASE.BEGIN_INDEX, BASE.END_INDEX), ("<!-- BEGIN V1.5.0 MODULE TRUTH INDEX -->", "<!-- END V1.5.0 MODULE TRUTH INDEX -->")):
        if begin in text and end in text:
            start = text.index(begin); finish = text.index(end, start) + len(end); text = text[:start] + text[finish:]
    block = "\n".join([
        "<!-- BEGIN V1.5.0 MODULE TRUTH INDEX -->",
        "## V1.5.0 machine-verified module truth",
        "",
        f"The current Cargo workspace contains `{value['module_count']}` crates. Exact source hashes, internal dependencies, public lexical declarations and discovered tests are bound in `{TRUTH_PATH.as_posix()}`.",
        "",
        "```text",
        "python scripts/render_module_source_truth_v1_5_0.py --check",
        "```",
        "<!-- END V1.5.0 MODULE TRUTH INDEX -->",
    ])
    return text.rstrip() + "\n\n" + block + "\n"


def render(root: Path, write: bool) -> None:
    value = truth(root)
    expected = BASE.dump_yaml(value)
    path = root / TRUTH_PATH
    if write: path.parent.mkdir(parents=True, exist_ok=True); path.write_text(expected, encoding="utf-8")
    elif not path.is_file() or path.read_text(encoding="utf-8") != expected: raise SystemExit("module source truth drift")
    for module in value["modules"]:
        expected_doc = BASE.module_doc_expected(root, module)
        doc = root / module["module_guide"]
        if write: doc.write_text(expected_doc, encoding="utf-8")
        elif doc.read_text(encoding="utf-8") != expected_doc: raise SystemExit(f"module guide drift: {doc}")
    expected_index = index_expected(root, value)
    index = root / "docs/modules/README.md"
    if write: index.write_text(expected_index, encoding="utf-8")
    elif index.read_text(encoding="utf-8") != expected_index: raise SystemExit("module index drift")


def main() -> int:
    parser = argparse.ArgumentParser(); group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--write", action="store_true"); group.add_argument("--check", action="store_true")
    args = parser.parse_args(); render(ROOT, args.write); print("PASS V1.5.0 module source truth"); return 0


if __name__ == "__main__": raise SystemExit(main())
'''


def module_validator_source() -> str:
    baseline = repr(set(BASELINE_CRATES))
    return f'''#!/usr/bin/env python3
from __future__ import annotations

import re
import tomllib
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE = {baseline}
EXEMPT = {{"README.md", "MODULE_DOCUMENTATION_STANDARD_V1.md", "MODULE_DOCUMENTATION_STANDARD_V2.md"}}


def members() -> dict[str, Path]:
    data = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8")); result = {{}}
    for entry in data["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if not (path / "Cargo.toml").is_file(): continue
            cargo = tomllib.loads((path / "Cargo.toml").read_text(encoding="utf-8")); result[cargo["package"]["name"]] = path
    return result


def main() -> int:
    workspace = members(); names = set(workspace)
    missing_baseline = BASELINE - names
    if missing_baseline: raise SystemExit(f"historical V1.4.4 crate disappeared: {{sorted(missing_baseline)}}")
    truth_path = ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml"
    if not truth_path.is_file(): truth_path = ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml"
    truth = yaml.safe_load(truth_path.read_text(encoding="utf-8")); truth_names = {{item["crate"] for item in truth["modules"]}}
    if truth_names != names or truth["module_count"] != len(names): raise SystemExit("current module truth/workspace mismatch")
    docs = ROOT / "docs/modules"
    for name in sorted(names):
        path = docs / f"{{name}}.md"
        if not path.is_file(): raise SystemExit(f"missing module guide: {{name}}")
        text = path.read_text(encoding="utf-8")
        for token in ("## Public API", "BEGIN GENERATED V1.4.7 PUBLIC API TRUTH", "BEGIN GENERATED V1.4.7 MODULE FACTS", "## Known gaps", "## Traceability"):
            if token not in text: raise SystemExit(f"{{name}}: missing {{token}}")
    orphan = {{path.name for path in docs.glob("*.md") if path.name not in EXEMPT and path.stem not in names}}
    if orphan: raise SystemExit(f"orphan module guides: {{sorted(orphan)}}")
    print(f"PASS successor-aware module documentation: {{len(names)}} crates; historical baseline {{len(BASELINE)}} retained")
    return 0


if __name__ == "__main__": raise SystemExit(main())
'''


def module_validator_test() -> str:
    return r'''from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("validator", ROOT / "scripts/validate_module_documentation_v1_4_4.py")
assert SPEC and SPEC.loader
VALIDATOR = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(VALIDATOR)


class ModuleDocumentationTests(unittest.TestCase):
    def test_current_workspace_retains_historical_baseline_and_all_guides(self) -> None:
        workspace = VALIDATOR.members()
        self.assertTrue(VALIDATOR.BASELINE.issubset(workspace))
        self.assertGreaterEqual(len(workspace), len(VALIDATOR.BASELINE))
        for name in workspace:
            self.assertTrue((ROOT / "docs/modules" / f"{name}.md").is_file())

    def test_validator_passes_current_successor(self) -> None:
        self.assertEqual(0, VALIDATOR.main())


if __name__ == "__main__": unittest.main()
'''


def v147_successor_validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import subprocess
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
BASELINE = "54d524214df443752a2ecaeff6d4a05625bf52c7"
CLAIMS = {"qualification": False, "compatibility_claim": False, "selected_candidates": [], "selection_effect": "NONE", "production_authority": False, "migration_authority": False, "release_authority": False, "authority_effect": "NONE"}


def main() -> int:
    required = [
        "docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md",
        "planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml",
        "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml",
        "planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml",
    ]
    for path in required:
        if not (ROOT / path).is_file(): raise SystemExit(f"missing inherited V1.4.7 object: {path}")
    for path in ("planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml", "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml"):
        if yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))["claims"] != CLAIMS: raise SystemExit("V1.4.7 authority drift")
    subprocess.run(["git", "merge-base", "--is-ancestor", BASELINE, "HEAD"], cwd=ROOT, check=True)
    current = (ROOT / "docs/CURRENT_DOCUMENTATION.md").read_text(encoding="utf-8")
    if "HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md" not in current and "HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md" not in current:
        raise SystemExit("current documentation lost V1.4.7 lineage")
    print("PASS inherited V1.4.7 lineage and authority boundary")
    return 0


if __name__ == "__main__": raise SystemExit(main())
'''


def v147_successor_tests() -> str:
    return r'''from __future__ import annotations

import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]


class V147SuccessorTests(unittest.TestCase):
    def test_v147_objects_remain_and_do_not_claim_external_closure(self) -> None:
        receipt = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_4_6_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text(encoding="utf-8"))
        self.assertEqual([], receipt["external_or_control_blockers_closed"])
        self.assertEqual("NONE", receipt["claims"]["authority_effect"])

    def test_current_module_truth_covers_workspace_successor(self) -> None:
        path = ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml"
        self.assertTrue(path.is_file())
        value = yaml.safe_load(path.read_text(encoding="utf-8"))
        self.assertGreaterEqual(value["module_count"], 19)


if __name__ == "__main__": unittest.main()
'''


def plan_doc(baseline: str, tree: str) -> str:
    return f'''# HeptaBao Plan V1.5.0 — Control Plane Vertical Slice

## 1. Baseline

This tranche starts from reviewed V1.4.7 integration commit `{baseline}`, tree `{tree}`. V1.4.7 repository blockers `HB-BLK-REPO-059..062` are carried as closed in repository scope by the post-merge receipt. Control and external blockers remain open.

## 2. Objective

Implement a mandatory in-process control-plane vertical slice rather than another planning-only layer:

1. canonical hierarchical namespace identities;
2. deterministic policy evaluation with explicit deny precedence;
3. entity/group snapshots and policy union;
4. namespace-scoped, TTL/use-limited, revocable token records;
5. renewable and revocable lease state;
6. typed mount resolution and plugin descriptors with no fallback routing;
7. versioned KV with CAS, soft delete, undelete and irreversible destroy;
8. one request pipeline that binds request identity, token, identity, policy, mount, audit intent, effect, audit outcome and idempotent completion;
9. outcome-unknown fencing after a possible effect;
10. successor-aware documentation truth for the expanded Cargo workspace.

## 3. Mandatory request ordering

```text
request-id replay/conflict check
→ namespace active check
→ token validation
→ identity/group snapshot
→ policy union and explicit-deny evaluation
→ longest-prefix mount resolution
→ audit intent
→ single token-use consumption
→ versioned KV effect
→ audit outcome
→ completed request cache or outcome-unknown fence
```

An audit-intent failure has no KV effect. If the KV effect succeeds but audit outcome is uncertain, the request is fenced as outcome unknown; a byte-identical retry does not repeat the effect, and a changed descriptor with the same request ID is rejected. Explicit reconciliation is required before completion.

## 4. Security boundary

The token crate models already-authenticated opaque token IDs; it is not a production bearer-secret authenticator. The in-memory audit and KV providers are deterministic development implementations. Secret values are redacted from Debug output and absent from audit metadata. Production storage, cryptography, transport, HSM/KMS, HA, backup, migration and compatibility qualification remain separate work.

## 5. New repository blockers

`HB-BLK-REPO-063..071` cover namespace, policy, identity, token/lease, typed mounts/plugin contracts, KV versioning, mandatory request ordering/idempotency, successor module truth and exact head/merge CI. They are source implemented by this candidate and remain review-required until current exact-head and prospective-merge gates plus independent review complete.

## 6. Required gates

```text
python scripts/render_module_source_truth_v1_5_0.py --check
python scripts/validate_plan_v1_5_0.py
python -m unittest discover -s tests/plan -p 'test_plan_v1_5_0.py' -v
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

## 7. Completion and nonclaims

This tranche closes only repository implementation gaps after review and merge. It does not close `HB-BLK-CTRL-001` or `HB-BLK-EXT-001..007`, establish OpenBao compatibility, select production providers, qualify a platform, or grant production, migration or release authority.
'''


def workflow() -> str:
    return '''name: HeptaBao V1.5.0 control-plane vertical slice

on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches:
      - integration/v1.4.4-technical-candidate

permissions:
  contents: read

concurrency:
  group: v1.5.0-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
  cancel-in-progress: true

jobs:
  validate:
    name: v1.5.0 / pull_request / ${{ matrix.source_kind }}
    runs-on: ubuntu-24.04
    timeout-minutes: 150
    permissions:
      contents: read
      pull-requests: read
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
      - name: Checkout immutable source
        uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1
        with:
          ref: ${{ env.SOURCE_SHA }}
          fetch-depth: 0
          persist-credentials: false
      - name: Bind exact head or prospective merge
        shell: bash
        run: |
          set -euo pipefail
          test "$(git rev-parse HEAD)" = "$SOURCE_SHA"
          if [[ "$SOURCE_KIND" == "prospective-merge" ]]; then
            read -r merge first second extra <<<"$(git rev-list --parents -n 1 HEAD)"
            test "$merge" = "$SOURCE_SHA"; test "$first" = "$BASE_SHA"; test "$second" = "$HEAD_SHA"; test -z "${extra:-}"
          else
            test "$SOURCE_SHA" = "$HEAD_SHA"
          fi
      - name: Install Python
        uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-plan.txt
      - name: Validate plans and all inherited contracts
        shell: bash
        run: |
          set -euo pipefail
          python -m pip install --disable-pip-version-check --requirement requirements-plan.txt
          python scripts/render_module_source_truth_v1_5_0.py --check
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


def current_docs() -> str:
    return '''# HeptaBao Current Documentation

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md` |
| current status | `planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_5_0.yaml` |
| current module truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml` |
| module standard | `docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md` |
| control-plane architecture | `docs/architecture/HEPTABAO_CONTROL_PLANE_REQUEST_PIPELINE_V1.md` |
| V1.4.7 post-merge receipt | `planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| current gate | `.github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml` |

## Supersession chain

```text
V1.4.6 authoritative recovery
  → V1.4.7 post-merge truth and external admission
  → V1.5.0 control-plane vertical slice
```

## Current implementation scope

The current workspace contains the inherited security/recovery kernel plus namespace, policy, identity, token, lease, mount/system, plugin-contract, versioned-KV and mandatory control-plane crates. The development control plane enforces request-ID conflict detection, namespace scope, token validation, identity/policy evaluation, typed mount dispatch, audit intent before effect, audit outcome after effect and outcome-unknown fencing.

The token contract begins after bearer authentication, and the current providers are in-memory development providers. No transport, production cryptographic custody, durable composition root, HA, backup, migration or broad compatibility claim follows from this source.

## Open authority boundary

`HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain open. Templates and repository CI cannot manufacture live branch rules, independent accountable identities, legal disposition, 24x7 operation, isolated signing custody, restricted Oracle transfer, power-cut evidence or independently controlled reproduction.

```text
qualification=false
compatibility_claim=false
production_authority=false
migration_authority=false
release_authority=false
authority_effect=NONE
```
'''


def architecture_doc() -> str:
    return '''# HeptaBao Control-Plane Request Pipeline V1

## Trust boundaries

The caller supplies an already-parsed request ID, namespace ID, authenticated token ID, operation and monotonic time. Namespace, token, entity, policies and mount are re-resolved inside the control plane; no caller-provided authorization decision is accepted.

## Happens-before contract

```text
request replay/conflict check
  hb namespace active check
  hb token validation
  hb identity snapshot
  hb policy decision
  hb mount resolution
  hb audit intent
  hb token-use consumption
  hb KV effect
  hb audit outcome
  hb completed cache
```

A failure before audit intent creates no KV effect. KV operations validate complete version sets before destructive mutation. A successful effect followed by an uncertain audit outcome becomes `AuditOutcomeUnknown`; the ledger retains the exact request digest and response, rejects automatic retry and requires `confirm_outcome` after external reconciliation.

## Idempotency

A completed request with the same descriptor returns the cached response and does not consume another token use or create another KV version. Reusing the request ID with any changed descriptor returns `RequestIdConflict`. In-progress and outcome-unknown states never re-enter the effect.

## Secret handling

Secret values participate in the request digest so altered retries conflict, but Debug representations expose only length. Audit events contain request ID, namespace, resource, capability and outcome—not token bearer material or KV bytes.

## Current limitations

The control plane is synchronous and in-memory. Durable request-ledger integration, production audit, bearer authentication, seal/barrier integration, leases with external callbacks, network transport, HA replication and compatibility qualification are later tranches.
'''


def status_doc(baseline: str, tree: str) -> dict[str, Any]:
    return {
        "schema": "heptabao.v1-5-0-control-plane-status.v1", "plan_id": PLAN_ID, "revision": "1.5.0",
        "status": "SOURCE_IMPLEMENTED_EXACT_HEAD_MERGE_AND_INDEPENDENT_REVIEW_REQUIRED",
        "current_plan": "docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md",
        "current_blocker_register": "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml",
        "normative_manifest": "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_5_0.yaml",
        "source_baseline": {"commit": baseline, "tree": tree},
        "closed_repository_scope_carried_forward": [f"HB-BLK-REPO-{i:03d}" for i in range(49, 63)],
        "implementation": {name.replace("heptabao-", "").replace("-", "_"): "IMPLEMENTED_SOURCE" for name in NEW_CRATES},
        "repository_open": [f"HB-BLK-REPO-{i:03d}" for i in range(63, 72)],
        "external_open": ["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{i:03d}" for i in range(1, 8)]],
        "product_gaps_carried_forward": [
            "production composition root with durable providers", "bearer authentication and production cryptographic token protection",
            "production KMS or HSM custody", "remote rollback anchor and qualified recovery target", "non-Linux qualification",
            "retention backup custody and restore drills", "Raft HA replication and snapshots", "online migration and mixed-version operation",
            "full OpenBao compatibility", "CLI Agent Proxy and production operations surface",
        ],
        "claims": CLAIMS,
    }


def blockers_doc(baseline: str, tree: str) -> dict[str, Any]:
    titles = [
        "namespace identity and hierarchy were not implemented", "policy evaluation and deny precedence were not implemented",
        "identity and group policy snapshots were not implemented", "token and lease lifetime revocation semantics were not implemented",
        "typed mount and plugin contracts with no fallback were not implemented", "versioned KV CAS delete undelete and destroy were not implemented",
        "mandatory request ordering idempotency and outcome-unknown fencing were absent", "module coverage gate rejected legitimate successor crates",
        "expanded control plane lacked exact-head and prospective-merge closure",
    ]
    evidence = [
        ["crates/heptabao-namespace"], ["crates/heptabao-policy"], ["crates/heptabao-identity"],
        ["crates/heptabao-token", "crates/heptabao-lease"], ["crates/heptabao-system", "crates/heptabao-plugin-contracts"],
        ["crates/heptabao-kv"], ["crates/heptabao-control-plane", "docs/architecture/HEPTABAO_CONTROL_PLANE_REQUEST_PIPELINE_V1.md"],
        ["scripts/validate_module_documentation_v1_4_4.py", "scripts/render_module_source_truth_v1_5_0.py"],
        [".github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml"],
    ]
    added = []
    for offset, title in enumerate(titles, 63):
        added.append({"id": f"HB-BLK-REPO-{offset:03d}", "class": "REPOSITORY_CONTROLLED", "severity": "CRITICAL" if offset in {64, 69} else "HIGH", "title": title, "state": "IMPLEMENTED_SOURCE_REVIEW_REQUIRED", "closure_criteria": ["typed source implementation exists", "positive and hostile tests pass", "module guide and source truth are current", "exact head and prospective merge pass before closure"], "evidence": evidence[offset - 63], "closure_receipt_required": True})
    return {
        "schema": "heptabao.blocker-register-extension.v1_5_0", "plan_id": PLAN_ID, "revision": "1.5.0", "status": "ACTIVE_FAIL_CLOSED",
        "inherits": "planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml", "source_baseline": {"commit": baseline, "tree": tree},
        "closed_carried_forward": [{"id": f"HB-BLK-REPO-{i:03d}", "state": "CLOSED_REPOSITORY_SCOPE"} for i in range(49, 63)],
        "added_blockers": added, "external_and_control_blockers_carried_forward": ["HB-BLK-CTRL-001", *[f"HB-BLK-EXT-{i:03d}" for i in range(1, 8)]],
        "product_gaps_carried_forward": status_doc(baseline, tree)["product_gaps_carried_forward"], "claims": CLAIMS,
    }


def post_merge_receipt(baseline: str, tree: str, head: str) -> dict[str, Any]:
    return {
        "schema": "heptabao.repository-post-merge-closure-receipt.v1", "plan_id": PLAN_ID,
        "repository": {"id": REPO_ID, "full_name": REPO}, "pull_request": 63,
        "reviewed_head_commit": head, "merge_commit": baseline, "merge_tree": tree,
        "reviewers": [
            {"github_login": "ProfHepta", "state": "APPROVED", "scope": "repository-change-review"},
            {"github_login": "Tomasrgbsf", "state": "APPROVED", "scope": "repository-change-review"},
        ],
        "closed_repository_blockers": [f"HB-BLK-REPO-{i:03d}" for i in range(59, 63)],
        "external_or_control_blockers_closed": [], "claims": CLAIMS,
    }


def plan_validator() -> str:
    return r'''#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import subprocess
import tomllib
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]
NEW = {"heptabao-namespace", "heptabao-policy", "heptabao-identity", "heptabao-token", "heptabao-lease", "heptabao-system", "heptabao-plugin-contracts", "heptabao-kv", "heptabao-control-plane"}
CLAIMS = {"qualification": False, "compatibility_claim": False, "selected_candidates": [], "selection_effect": "NONE", "production_authority": False, "migration_authority": False, "release_authority": False, "authority_effect": "NONE"}


def sha(path: Path) -> str: return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    status = yaml.safe_load((ROOT / "planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml").read_text(encoding="utf-8"))
    blockers = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml").read_text(encoding="utf-8"))
    receipt = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text(encoding="utf-8"))
    for value in (status, blockers, receipt):
        if value["claims"] != CLAIMS: raise SystemExit("authority drift")
    baseline = status["source_baseline"]
    tree = subprocess.check_output(["git", "rev-parse", f"{baseline['commit']}^{{tree}}"], cwd=ROOT, text=True).strip()
    if tree != baseline["tree"]: raise SystemExit("baseline tree drift")
    subprocess.run(["git", "merge-base", "--is-ancestor", baseline["commit"], "HEAD"], cwd=ROOT, check=True)
    cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8")); names = set()
    for entry in cargo["workspace"]["members"]:
        for path in ROOT.glob(entry):
            if (path / "Cargo.toml").is_file(): names.add(tomllib.loads((path / "Cargo.toml").read_text(encoding="utf-8"))["package"]["name"])
    if not NEW.issubset(names): raise SystemExit(f"missing new crates: {sorted(NEW - names)}")
    truth = yaml.safe_load((ROOT / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml").read_text(encoding="utf-8"))
    if {item["crate"] for item in truth["modules"]} != names: raise SystemExit("module truth mismatch")
    if [item["id"] for item in blockers["added_blockers"]] != [f"HB-BLK-REPO-{i:03d}" for i in range(63, 72)]: raise SystemExit("blocker set mismatch")
    if any(item["state"] != "IMPLEMENTED_SOURCE_REVIEW_REQUIRED" for item in blockers["added_blockers"]): raise SystemExit("blockers must remain review required")
    source = (ROOT / "crates/heptabao-control-plane/src/lib.rs").read_text(encoding="utf-8")
    for token in ("AuditBeforeIntent", "AuditOutcomeUnknown", "RequestIdConflict", "OutcomeUnknown", "record_intent", "record_outcome", "confirm_outcome"):
        if token not in source: raise SystemExit(f"control-plane invariant missing: {token}")
    workflow = (ROOT / ".github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml").read_text(encoding="utf-8")
    if "pull_request:" not in workflow or "push:" in workflow or "prospective-merge" not in workflow: raise SystemExit("workflow admission drift")
    manifest = yaml.safe_load((ROOT / "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_5_0.yaml").read_text(encoding="utf-8"))
    for item in manifest["files"]:
        path = ROOT / item["path"]
        if not path.is_file() or sha(path) != item["sha256"]: raise SystemExit(f"manifest mismatch: {item['path']}")
    subprocess.run(["python", "scripts/render_module_source_truth_v1_5_0.py", "--check"], cwd=ROOT, check=True)
    print("PASS HeptaBao V1.5.0 control-plane vertical slice")
    return 0


if __name__ == "__main__": raise SystemExit(main())
'''


def plan_tests() -> str:
    return r'''from __future__ import annotations

import tomllib
import unittest
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[2]
NEW = {"heptabao-namespace", "heptabao-policy", "heptabao-identity", "heptabao-token", "heptabao-lease", "heptabao-system", "heptabao-plugin-contracts", "heptabao-kv", "heptabao-control-plane"}


class PlanV150Tests(unittest.TestCase):
    def test_new_crates_are_workspace_members_with_guides(self) -> None:
        cargo = tomllib.loads((ROOT / "Cargo.toml").read_text(encoding="utf-8")); names = set()
        for entry in cargo["workspace"]["members"]:
            for path in ROOT.glob(entry):
                if (path / "Cargo.toml").is_file(): names.add(tomllib.loads((path / "Cargo.toml").read_text(encoding="utf-8"))["package"]["name"])
        self.assertTrue(NEW.issubset(names))
        for name in NEW: self.assertTrue((ROOT / "docs/modules" / f"{name}.md").is_file())

    def test_blockers_and_external_boundary_are_fail_closed(self) -> None:
        value = yaml.safe_load((ROOT / "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml").read_text(encoding="utf-8"))
        self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(63, 72)], [item["id"] for item in value["added_blockers"]])
        self.assertEqual("NONE", value["claims"]["authority_effect"])
        self.assertIn("HB-BLK-EXT-007", value["external_and_control_blockers_carried_forward"])

    def test_post_merge_receipt_closes_only_repository_scope(self) -> None:
        value = yaml.safe_load((ROOT / "planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text(encoding="utf-8"))
        self.assertEqual([], value["external_or_control_blockers_closed"])
        self.assertEqual([f"HB-BLK-REPO-{i:03d}" for i in range(59, 63)], value["closed_repository_blockers"])


if __name__ == "__main__": unittest.main()
'''


def standard_v2() -> str:
    return '''# HeptaBao Module Documentation Standard V2

Every Cargo workspace crate must have one guide under `docs/modules/`. Each guide retains purpose, maturity, dependency direction, Public API, state invariants, failure/retry semantics, data formats, security, tests, extension rules, operations, known gaps and traceability.

Machine-bound facts—Cargo and source SHA-256, workspace-internal dependencies, public lexical declarations and discovered tests—are generated into `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml` and every guide. Run:

```text
python scripts/render_module_source_truth_v1_5_0.py --write
python scripts/render_module_source_truth_v1_5_0.py --check
```

The parser is a bounded lexical inventory, not Rust name resolution or a compatibility promise. Hand-edited generated blocks, missing successor guides, stale dependencies or removed tests fail closed. Historical V1.4.4 coverage remains immutable evidence for its original 19 crates; successor validation requires that baseline to remain present and every added crate to satisfy V2.
'''


def materialize(root: Path) -> None:
    baseline = sh(root, "git", "rev-parse", "HEAD")
    tree = sh(root, "git", "rev-parse", "HEAD^{tree}")
    head = sh(root, "git", "rev-parse", "HEAD^2") if len(sh(root, "git", "rev-list", "--parents", "-n", "1", "HEAD").split()) > 2 else baseline
    update_workspace(root)
    crates: dict[str, tuple[str, dict[str, str]]] = {
        "heptabao-namespace": (namespace_rs(), {}),
        "heptabao-policy": (policy_rs(), {"heptabao-namespace": "../heptabao-namespace"}),
        "heptabao-identity": (identity_rs(), {}),
        "heptabao-token": (token_rs(), {"heptabao-identity": "../heptabao-identity", "heptabao-namespace": "../heptabao-namespace"}),
        "heptabao-lease": (lease_rs(), {"heptabao-namespace": "../heptabao-namespace"}),
        "heptabao-system": (system_rs(), {"heptabao-namespace": "../heptabao-namespace"}),
        "heptabao-plugin-contracts": (plugin_contracts_rs(), {}),
        "heptabao-kv": (kv_rs(), {"heptabao-namespace": "../heptabao-namespace", "heptabao-system": "../heptabao-system"}),
        "heptabao-control-plane": (control_plane_rs(), {"heptabao-identity": "../heptabao-identity", "heptabao-kv": "../heptabao-kv", "heptabao-namespace": "../heptabao-namespace", "heptabao-policy": "../heptabao-policy", "heptabao-system": "../heptabao-system", "heptabao-token": "../heptabao-token"}),
    }
    purposes = {
        "heptabao-namespace": ("Own canonical namespace IDs, paths, hierarchy and active-state resolution.", "Development source contract.", "Foundation crate with no workspace dependencies.", ["Root is immutable and active.", "Every non-root namespace has an active parent.", "ID and path uniqueness are independent constraints."], ["No durable provider or namespace deletion workflow."]),
        "heptabao-policy": ("Evaluate typed capabilities against namespace-bound path rules with global explicit-deny precedence.", "Development authorization kernel.", "Depends only on namespace identities.", ["Explicit deny terminates evaluation.", "No match is deny.", "Policy union is deterministic through ordered names."], ["No HCL parser, templating or sudo-root policy language."]),
        "heptabao-identity": ("Maintain entity and group membership and emit immutable policy snapshots.", "Development identity contract.", "No workspace dependencies.", ["Inactive identities cannot produce snapshots.", "Group policy union is set-based and deterministic.", "Stable IDs are distinct from display aliases."], ["No external identity provider or alias lifecycle."]),
        "heptabao-token": ("Model already-authenticated token identity, namespace scope, policies, TTL, use limits and revocation.", "Development post-authentication token state.", "Depends on namespace and identity IDs.", ["Namespace mismatch fails closed.", "Expired, revoked and exhausted tokens cannot be consumed.", "One successful control-plane effect consumes at most one use."], ["No bearer-secret hashing, wrapping, orphan hierarchy or periodic tokens."]),
        "heptabao-lease": ("Model renewable and revocable lease expiry state.", "Development lease state.", "Depends on namespace IDs.", ["Expiry is monotonic caller-supplied time.", "Revocation dominates renewal.", "Non-renewable leases reject renewal."], ["No external revocation callbacks or durable expiration queue."]),
        "heptabao-system": ("Own typed namespace mount entries and longest-prefix routing without implicit fallback.", "Development mount table.", "Depends on namespace IDs.", ["Mount paths are canonical.", "Resolution is namespace-local.", "Unsupported mount kinds never fall back to KV."], ["No remount, tune, plugin process or durable catalog."]),
        "heptabao-plugin-contracts": ("Bind plugin identity, executable digest, protocol version and declared capabilities.", "Contract only; no process execution.", "No workspace dependencies.", ["Digest is exact lowercase SHA-256.", "Protocol version zero is rejected.", "Capabilities are explicit."], ["No sandbox, transport, handshake or runtime host."]),
        "heptabao-kv": ("Provide an in-memory versioned KV model with CAS, delete, undelete and irreversible destroy.", "Development semantic provider.", "Depends on namespace and mount IDs.", ["Version numbers increase without reuse.", "CAS is checked before mutation.", "Destroy removes bytes and cannot be undone.", "Multi-version operations validate the complete set first."], ["No durable storage, compaction or encryption barrier integration."]),
        "heptabao-control-plane": ("Compose namespace, token, identity, policy, mount, audit and KV into one mandatory request path with idempotency.", "Development vertical slice.", "Depends on the V1.5 domain crates.", ["Audit intent happens before effect.", "Audit outcome happens after effect.", "Completed retries do not repeat effects.", "Outcome-unknown requests remain fenced.", "Request-ID descriptor conflicts fail closed."], ["No network server, durable request ledger, production audit or HA composition."]),
    }
    for name, (source, dependencies) in crates.items():
        write(root, f"crates/{name}/Cargo.toml", crate_toml(name, dependencies))
        write(root, f"crates/{name}/src/lib.rs", source)
        purpose = purposes[name]
        write(root, f"docs/modules/{name}.md", module_doc(name, *purpose))
    write(root, "scripts/render_module_source_truth_v1_5_0.py", module_renderer_source())
    write(root, "scripts/validate_module_documentation_v1_4_4.py", module_validator_source())
    write(root, "tests/plan/test_module_documentation_v1_4_4.py", module_validator_test())
    write(root, "scripts/validate_plan_v1_4_7.py", v147_successor_validator())
    write(root, "tests/plan/test_plan_v1_4_7.py", v147_successor_tests())
    write(root, "tests/plan/test_module_source_truth_v1_4_7.py", v147_successor_tests())
    write(root, "docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md", standard_v2())
    write(root, "docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md", plan_doc(baseline, tree))
    write(root, "docs/architecture/HEPTABAO_CONTROL_PLANE_REQUEST_PIPELINE_V1.md", architecture_doc())
    write(root, "planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml", yaml.safe_dump(status_doc(baseline, tree), sort_keys=False, width=120))
    write(root, "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml", yaml.safe_dump(blockers_doc(baseline, tree), sort_keys=False, width=120))
    write(root, "planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml", yaml.safe_dump(post_merge_receipt(baseline, tree, head), sort_keys=False, width=120))
    write(root, "docs/CURRENT_DOCUMENTATION.md", current_docs())
    write(root, ".github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml", workflow())
    write(root, "scripts/validate_plan_v1_5_0.py", plan_validator())
    write(root, "tests/plan/test_plan_v1_5_0.py", plan_tests())
    subprocess.run(["python", "scripts/render_module_source_truth_v1_5_0.py", "--write"], cwd=root, check=True)
    truth = yaml.safe_load((root / "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml").read_text(encoding="utf-8"))
    normative = [
        "docs/CURRENT_DOCUMENTATION.md", "docs/plan/HEPTABAO_PLAN_V1_5_0_CONTROL_PLANE_VERTICAL_SLICE.md",
        "docs/architecture/HEPTABAO_CONTROL_PLANE_REQUEST_PIPELINE_V1.md", "docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md",
        "planning/HEPTABAO_V1_5_0_CONTROL_PLANE_STATUS.yaml", "planning/HEPTABAO_BLOCKER_REGISTER_V1_5_0.yaml",
        "planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_5_0.yaml", "planning/evidence/repository/HEPTABAO_V1_4_7_POST_MERGE_CLOSURE_RECEIPT.yaml",
        "scripts/render_module_source_truth_v1_5_0.py", "scripts/validate_plan_v1_5_0.py", ".github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml",
    ] + [item["module_guide"] for item in truth["modules"]]
    manifest = {"schema": "heptabao.normative-document-manifest.v1_5_0", "plan_id": PLAN_ID, "revision": "1.5.0", "status": "CANDIDATE_EXACT_HEAD_MERGE_REVIEW_REQUIRED", "source_baseline": {"commit": baseline, "tree": tree}, "files": [{"path": path, "sha256": digest(root / path)} for path in sorted(set(normative))], "claims": CLAIMS}
    write(root, "planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_5_0.yaml", yaml.safe_dump(manifest, sort_keys=False, width=120))


def main() -> int:
    parser = argparse.ArgumentParser(); parser.add_argument("root", type=Path); args = parser.parse_args(); materialize(args.root.resolve()); return 0


if __name__ == "__main__": raise SystemExit(main())
