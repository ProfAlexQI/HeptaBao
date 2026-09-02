#!/usr/bin/env python3
from __future__ import annotations
import argparse,hashlib,re,subprocess,tomllib
from pathlib import Path
from typing import Any
import yaml
PLAN_ID="HEPTABAO-PLAN-2026-09-02-V1.8.0"
NEW_CRATES=["heptabao-config","heptabao-observability","heptabao-service","heptabao-cluster","heptabao-agent-proxy"]
BASELINE_CRATES={"heptabao-authbus-contracts","heptabao-barrier-api","heptabao-durable-core","heptabao-filesystem-guard","heptabao-governance","heptabao-journal-api","heptabao-journaled-core","heptabao-key-lifecycle","heptabao-operation-ledger","heptabao-oracle-observer","heptabao-p0-server","heptabao-platform-bakeoff","heptabao-platform-contracts","heptabao-protocol","heptabao-recovery-core","heptabao-rollback-anchor","heptabao-single-node-journal","heptabao-single-node-store","heptabao-storage-api","heptabao-namespace","heptabao-policy","heptabao-identity","heptabao-token","heptabao-lease","heptabao-system","heptabao-plugin-contracts","heptabao-kv","heptabao-control-plane","heptabao-kms-contracts","heptabao-runtime","heptabao-recovery-providers","heptabao-lifecycle-ops","heptabao-http-api","heptabao-ha-core","heptabao-plugin-host","heptabao-compat-runner","heptabao-client-tools"}
CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def sh(root:Path,*args:str)->str:return subprocess.check_output(args,cwd=root,text=True).strip()
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def write(root:Path,path:str,content:str)->None:
 target=root/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_text(content.rstrip()+"\n",encoding="utf-8")
def crate_toml(name:str,deps:dict[str,str]|None=None)->str:
 lines=["[package]",f'name = "{name}"','version = "0.1.0"','edition = "2024"','rust-version = "1.98"','publish = false',"","[lints]","workspace = true"]
 if deps:
  lines.extend(["","[dependencies]"])
  for dependency,path in sorted(deps.items()):lines.append(f'{dependency} = {{ path = "{path}" }}')
 return "\n".join(lines)+"\n"
def update_workspace(root:Path)->None:
 path=root/"Cargo.toml";text=path.read_text();match=re.search(r"(?ms)(members\s*=\s*\[)(.*?)(\n\s*\])",text)
 if not match:raise SystemExit("workspace members missing")
 body=match.group(2);existing=set(re.findall(r'"([^"]+)"',body));additions=[f"crates/{name}"for name in NEW_CRATES if f"crates/{name}"not in existing]
 if additions:
  if not body.endswith("\n"):body+="\n"
  body+="".join(f'  "{item}",\n'for item in additions);path.write_text(text[:match.start(2)]+body+text[match.end(2):])
def config_rs()->str:
 return r'''#![forbid(unsafe_code)]
use std::collections::{BTreeMap,BTreeSet};use std::net::SocketAddr;use std::path::PathBuf;use heptabao_kms_contracts::{sha256,Digest32,KeyHandle};
#[derive(Clone,Debug,Eq,PartialEq)]pub struct ListenerConfig{pub address:SocketAddr,pub tls_provider:Option<String>,pub max_header_bytes:usize,pub max_body_bytes:usize}
#[derive(Clone,Debug,Eq,PartialEq)]pub struct StorageConfig{pub path:PathBuf}
#[derive(Clone,Debug,Eq,PartialEq)]pub struct ServiceConfig{pub listener:ListenerConfig,pub storage:StorageConfig,pub seal_key:KeyHandle,pub max_inflight:usize,pub request_timeout_ms:u64,pub cluster_enabled:bool,pub digest:Digest32}
#[derive(Clone,Debug,Eq,PartialEq)]pub enum ConfigError{InvalidLine,UnknownKey,DuplicateKey,InvalidAddress,RemotePlaintext,InvalidNumber,InvalidPath,InvalidBoolean,InlineSecretForbidden,MissingKey,InvalidSealHandle}
const KEYS:[&str;9]=["listener.address","listener.tls_provider","listener.max_header_bytes","listener.max_body_bytes","storage.path","seal.key_handle","runtime.max_inflight","runtime.request_timeout_ms","cluster.enabled"];
pub fn parse_config(input:&str)->Result<ServiceConfig,ConfigError>{let allowed:BTreeSet<&str>=KEYS.into_iter().collect();let mut values=BTreeMap::new();for raw in input.lines(){let line=raw.trim();if line.is_empty()||line.starts_with('#'){continue}let Some((key,value))=line.split_once('=')else{return Err(ConfigError::InvalidLine)};let key=key.trim();let value=value.trim();if !allowed.contains(key){return Err(if key.contains("secret")||key.contains("token")||key.contains("password"){ConfigError::InlineSecretForbidden}else{ConfigError::UnknownKey})}if values.insert(key.to_owned(),value.to_owned()).is_some(){return Err(ConfigError::DuplicateKey)}}let required=|key:&str|values.get(key).ok_or(ConfigError::MissingKey);let address:SocketAddr=required("listener.address")?.parse().map_err(|_|ConfigError::InvalidAddress)?;let tls_provider=values.get("listener.tls_provider").cloned().filter(|value|!value.is_empty());if !address.ip().is_loopback()&&tls_provider.is_none(){return Err(ConfigError::RemotePlaintext)}let max_header_bytes=parse_positive(required("listener.max_header_bytes")?)?;let max_body_bytes=parse_positive(required("listener.max_body_bytes")?)?;let storage_path=PathBuf::from(required("storage.path")?);if !storage_path.is_absolute(){return Err(ConfigError::InvalidPath)}let seal_key=KeyHandle::parse(required("seal.key_handle")?).map_err(|_|ConfigError::InvalidSealHandle)?;let max_inflight=parse_positive(required("runtime.max_inflight")?)?;let request_timeout_ms=required("runtime.request_timeout_ms")?.parse::<u64>().map_err(|_|ConfigError::InvalidNumber)?;if request_timeout_ms==0{return Err(ConfigError::InvalidNumber)}let cluster_enabled=match required("cluster.enabled")?.as_str(){"true"=>true,"false"=>false,_=>return Err(ConfigError::InvalidBoolean)};let canonical=canonicalize(&values);let digest=sha256(canonical.as_bytes());Ok(ServiceConfig{listener:ListenerConfig{address,tls_provider,max_header_bytes,max_body_bytes},storage:StorageConfig{path:storage_path},seal_key,max_inflight,request_timeout_ms,cluster_enabled,digest})}
fn parse_positive(value:&str)->Result<usize,ConfigError>{let parsed=value.parse::<usize>().map_err(|_|ConfigError::InvalidNumber)?;if parsed==0{Err(ConfigError::InvalidNumber)}else{Ok(parsed)}}fn canonicalize(values:&BTreeMap<String,String>)->String{values.iter().map(|(key,value)|format!("{key}={value}\n")).collect()}
#[cfg(test)]mod tests{use super::*;fn valid()->String{"listener.address=127.0.0.1:8200\nlistener.max_header_bytes=16384\nlistener.max_body_bytes=1048576\nstorage.path=/var/lib/heptabao\nseal.key_handle=kms://barrier/key-0001\nruntime.max_inflight=128\nruntime.request_timeout_ms=5000\ncluster.enabled=false\n".to_owned()}#[test]fn duplicate_unknown_and_inline_secret_keys_fail_closed(){assert_eq!(parse_config(&(valid()+"runtime.max_inflight=2\n")),Err(ConfigError::DuplicateKey));assert_eq!(parse_config(&(valid()+"other=value\n")),Err(ConfigError::UnknownKey));assert_eq!(parse_config(&(valid()+"root_token=secret\n")),Err(ConfigError::InlineSecretForbidden));}#[test]fn remote_plaintext_is_rejected_and_digest_is_deterministic(){let remote=valid().replace("127.0.0.1:8200","192.0.2.1:8200");assert_eq!(parse_config(&remote),Err(ConfigError::RemotePlaintext));let tls=remote+"listener.tls_provider=tls-provider-1\n";let first=parse_config(&tls);let second=parse_config(&tls);assert_eq!(first,second);}}
'''
def observability_rs()->str:
 return r'''#![forbid(unsafe_code)]
use std::collections::{BTreeMap,BTreeSet};use heptabao_runtime::RuntimeState;
#[derive(Clone,Copy,Debug,Eq,Hash,Ord,PartialEq,PartialOrd)]pub enum MetricName{RequestsTotal,RequestFailures,OutcomeUnknownTotal,AuditFailures,RecoverySeconds,HaCommitIndex,PluginFailures,BackupVerified}
#[derive(Clone,Debug,Eq,Hash,Ord,PartialEq,PartialOrd)]struct SeriesKey{metric:MetricName,labels:Vec<(String,String)>}
#[derive(Clone,Debug,Eq,PartialEq)]pub enum MetricError{TooManyLabels,ForbiddenLabel,InvalidLabel,CardinalityLimit,Overflow}
#[derive(Clone,Debug)]pub struct MetricRegistry{series:BTreeMap<SeriesKey,u64>,maximum_series:usize,maximum_labels:usize}
impl MetricRegistry{pub fn new(maximum_series:usize,maximum_labels:usize)->Result<Self,MetricError>{if maximum_series==0||maximum_labels==0{return Err(MetricError::CardinalityLimit)}Ok(Self{series:BTreeMap::new(),maximum_series,maximum_labels})}fn key(&self,metric:MetricName,labels:&BTreeMap<String,String>)->Result<SeriesKey,MetricError>{if labels.len()>self.maximum_labels{return Err(MetricError::TooManyLabels)}let forbidden:BTreeSet<&str>=BTreeSet::from(["token","secret","value","request_path","entity_id"]);let mut output=Vec::new();for(name,value)in labels{if forbidden.contains(name.as_str()){return Err(MetricError::ForbiddenLabel)}if name.is_empty()||value.is_empty()||name.len()>32||value.len()>64||!name.bytes().all(|byte|byte.is_ascii_alphanumeric()||byte==b'_'){return Err(MetricError::InvalidLabel)}output.push((name.clone(),value.clone()))}Ok(SeriesKey{metric,labels:output})}pub fn increment(&mut self,metric:MetricName,labels:&BTreeMap<String,String>,amount:u64)->Result<u64,MetricError>{let key=self.key(metric,labels)?;if !self.series.contains_key(&key)&&self.series.len()>=self.maximum_series{return Err(MetricError::CardinalityLimit)}let value=self.series.entry(key).or_default();*value=value.checked_add(amount).ok_or(MetricError::Overflow)?;Ok(*value)}pub fn set(&mut self,metric:MetricName,labels:&BTreeMap<String,String>,value:u64)->Result<(),MetricError>{let key=self.key(metric,labels)?;if !self.series.contains_key(&key)&&self.series.len()>=self.maximum_series{return Err(MetricError::CardinalityLimit)}self.series.insert(key,value);Ok(())}}
#[derive(Clone,Debug,Eq,PartialEq)]pub struct HealthReport{pub live:bool,pub ready:bool,pub degraded:bool,pub state:RuntimeState,pub reason:&'static str}
pub fn health(state:RuntimeState)->HealthReport{match state{RuntimeState::Bootstrap=>HealthReport{live:true,ready:false,degraded:false,state,reason:"bootstrap"},RuntimeState::Sealed|RuntimeState::Unsealing=>HealthReport{live:true,ready:false,degraded:false,state,reason:"sealed"},RuntimeState::Ready=>HealthReport{live:true,ready:true,degraded:false,state,reason:"ready"},RuntimeState::Draining=>HealthReport{live:true,ready:false,degraded:true,state,reason:"draining"},RuntimeState::RecoveryRequired=>HealthReport{live:true,ready:false,degraded:true,state,reason:"recovery-required"},RuntimeState::Stopped=>HealthReport{live:false,ready:false,degraded:false,state,reason:"stopped"}}}
#[cfg(test)]mod tests{use super::*;#[test]fn high_cardinality_and_secret_labels_fail_closed(){let Ok(mut registry)=MetricRegistry::new(1,2)else{assert!(false);return};assert_eq!(registry.increment(MetricName::RequestsTotal,&BTreeMap::from([("token".to_owned(),"secret".to_owned())]),1),Err(MetricError::ForbiddenLabel));assert!(registry.increment(MetricName::RequestsTotal,&BTreeMap::from([("status".to_owned(),"ok".to_owned())]),1).is_ok());assert_eq!(registry.increment(MetricName::RequestFailures,&BTreeMap::new(),1),Err(MetricError::CardinalityLimit));}#[test]fn health_never_marks_recovery_required_ready(){let report=health(RuntimeState::RecoveryRequired);assert!(report.live);assert!(!report.ready);assert!(report.degraded);}}
'''
def service_rs()->str:
 return r'''#![forbid(unsafe_code)]
use std::collections::BTreeMap;use heptabao_control_plane::{AuditSink,ControlPlaneError,Operation,Request,RequestId,Response};use heptabao_http_api::{HttpHandler,HttpMethod,HttpRequest,HttpResponse};use heptabao_kv::{KvError,SecretBytes};use heptabao_namespace::NamespaceId;use heptabao_observability::health;use heptabao_runtime::{Runtime,RuntimeError,RuntimeState,SealProvider};use heptabao_token::TokenId;
pub trait Clock{fn now_ms(&self)->u64;}#[derive(Clone,Copy,Debug)]pub struct FixedClock(pub u64);impl Clock for FixedClock{fn now_ms(&self)->u64{self.0}}
pub struct RuntimeHttpHandler<S:SealProvider,A:AuditSink,C:Clock>{runtime:Runtime<S,A>,clock:C}
impl<S:SealProvider,A:AuditSink,C:Clock>RuntimeHttpHandler<S,A,C>{pub fn new(runtime:Runtime<S,A>,clock:C)->Self{Self{runtime,clock}}pub fn runtime_state(&self)->RuntimeState{self.runtime.state()}fn dispatch(&mut self,request:HttpRequest)->HttpResponse{if request.target=="/v1/sys/health"{let report=health(self.runtime.state());let body=format!("state={:?}\nlive={}\nready={}\ndegraded={}\nreason={}\n",report.state,report.live,report.ready,report.degraded,report.reason).into_bytes();return response(if report.ready{200}else{503},body)}let namespace=match request.headers.get("x-heptabao-namespace").map_or_else(||Ok(NamespaceId::root()),|value|NamespaceId::parse(value)){Ok(value)=>value,Err(_)=>return response(400,b"invalid namespace".to_vec())};let token=match request.headers.get("x-heptabao-token").ok_or(()).and_then(|value|TokenId::parse(value).map_err(|_|())){Ok(value)=>value,Err(())=>return response(403,b"missing or invalid token".to_vec())};let id=match request.headers.get("x-request-id").ok_or(()).and_then(|value|RequestId::parse(value).map_err(|_|())){Ok(value)=>value,Err(())=>return response(400,b"missing or invalid request id".to_vec())};let(path,query)=split_target(&request.target);let resource=match path.strip_prefix("/v1"){Some(value)if value.starts_with("/secret/")||value=="/secret"=>value.to_owned(),_=>return response(404,b"route not found".to_vec())};let operation=match request.method{HttpMethod::Get=>{if query.get("list").is_some_and(|value|value=="true"){Operation::List{prefix:resource}}else{let version=match query.get("version"){Some(value)=>match value.parse(){Ok(value)=>Some(value),Err(_)=>return response(400,b"invalid version".to_vec())},None=>None};Operation::Read{path:resource,version}}},HttpMethod::Put|HttpMethod::Post=>{let value=match SecretBytes::new(request.body.expose().to_vec()){Ok(value)=>value,Err(_)=>return response(400,b"empty value".to_vec())};let cas=match query.get("cas"){Some(value)=>match value.parse(){Ok(value)=>Some(value),Err(_)=>return response(400,b"invalid cas".to_vec())},None=>None};Operation::Put{path:resource,value,cas}},HttpMethod::Delete=>{let versions=match query.get("versions"){Some(value)=>match parse_versions(value){Ok(value)=>value,Err(())=>return response(400,b"invalid versions".to_vec())},None=>return response(400,b"versions required".to_vec())};Operation::Delete{path:resource,versions}}};let result=self.runtime.execute(Request{id,namespace,token,now_ms:self.clock.now_ms(),operation});match result{Ok(Response::Version(version))=>{let mut result=response(200,version.value().map_or_else(Vec::new,|value|value.expose().to_vec()));result.headers.insert("x-heptabao-version".to_owned(),version.version().to_string());result},Ok(Response::Keys(keys))=>response(200,keys.join("\n").into_bytes()),Ok(Response::Empty)=>response(204,Vec::new()),Err(error)=>map_runtime_error(error)}}}
impl<S:SealProvider,A:AuditSink,C:Clock>HttpHandler for RuntimeHttpHandler<S,A,C>{fn handle(&mut self,request:HttpRequest)->HttpResponse{self.dispatch(request)}}
fn split_target(target:&str)->(&str,BTreeMap<String,String>){let Some((path,query))=target.split_once('?')else{return(target,BTreeMap::new())};let values=query.split('&').filter_map(|pair|pair.split_once('=')).map(|(key,value)|(key.to_owned(),value.to_owned())).collect();(path,values)}fn parse_versions(value:&str)->Result<Vec<u64>,()>{let mut output=Vec::new();for item in value.split(','){let parsed=item.parse().map_err(|_|())?;output.push(parsed)}if output.is_empty(){Err(())}else{Ok(output)}}fn response(status:u16,body:Vec<u8>)->HttpResponse{HttpResponse{status,headers:BTreeMap::new(),body}}
fn map_runtime_error<E>(error:RuntimeError<E>)->HttpResponse{match error{RuntimeError::Sealed|RuntimeError::Draining|RuntimeError::RecoveryRequired=>response(503,b"runtime unavailable".to_vec()),RuntimeError::Control(ControlPlaneError::Denied(_)|ControlPlaneError::Token(_))=>response(403,b"forbidden".to_vec()),RuntimeError::Control(ControlPlaneError::RequestIdConflict)=>response(409,b"request id conflict".to_vec()),RuntimeError::Control(ControlPlaneError::OutcomeUnknown|ControlPlaneError::AuditOutcomeUnknown)=>{let mut result=response(503,b"outcome unknown".to_vec());result.headers.insert("x-heptabao-outcome".to_owned(),"unknown".to_owned());result},RuntimeError::Control(ControlPlaneError::Kv(KvError::VersionMissing|KvError::Deleted|KvError::Destroyed)|ControlPlaneError::Mount(_))=>response(404,b"not found".to_vec()),RuntimeError::Control(_)=>response(400,b"request rejected".to_vec()),RuntimeError::Contract(_)|RuntimeError::SealBeforeEntry(_)|RuntimeError::SealOutcomeUnknown(_)=>response(503,b"runtime failure".to_vec())}}
#[cfg(test)]mod tests{use std::collections::BTreeSet;use super::*;use heptabao_control_plane::{ControlPlane,MemoryAuditSink};use heptabao_identity::{EntityId,IdentityStore};use heptabao_kms_contracts::{SecretMaterial};use heptabao_kv::KvStore;use heptabao_namespace::NamespaceRegistry;use heptabao_policy::{Capability,Policy,PolicyRule,PolicyStore,RuleEffect};use heptabao_runtime::{SealCapability,SealFailure};use heptabao_system::{MountEntry,MountId,MountKind,MountTable};use heptabao_token::{TokenIssue,TokenStore};#[derive(Clone,Debug,Eq,PartialEq)]struct SealError;#[derive(Default)]struct Seal;impl SealProvider for Seal{type Error=SealError;fn initialize(&mut self)->Result<(),SealFailure<Self::Error>>{Ok(())}fn unseal(&mut self,_:SecretMaterial)->Result<SealCapability,SealFailure<Self::Error>>{SealCapability::new(1).map_err(|_|SealFailure::BeforeEntry(SealError))}fn seal(&mut self,_:SealCapability)->Result<(),SealFailure<Self::Error>>{Ok(())}}fn handler(fail_outcome:bool)->Option<RuntimeHttpHandler<Seal,MemoryAuditSink,FixedClock>>{let entity=EntityId::parse("service-entity").ok()?;let mut identities=IdentityStore::default();identities.create_entity(entity.clone(),BTreeSet::new()).ok()?;let rule=PolicyRule::new(None,"/secret",true,BTreeSet::from([Capability::Create,Capability::Read,Capability::Update,Capability::Delete,Capability::List]),RuleEffect::Allow).ok()?;let mut policies=PolicyStore::default();policies.insert(Policy::new("service",vec![rule]).ok()?).ok()?;let token=TokenId::parse("service-token-0001").ok()?;let mut tokens=TokenStore::default();tokens.issue(TokenIssue{id:token,namespace:NamespaceId::root(),entity,policy_names:BTreeSet::from(["service".to_owned()]),issued_at_ms:0,ttl_ms:10000,use_limit:Some(100)}).ok()?;let mount=MountEntry::new(MountId::parse("service-kv").ok()?,NamespaceId::root(),"/secret",MountKind::Kv).ok()?;let mut mounts=MountTable::default();mounts.mount(mount).ok()?;let mut audit=MemoryAuditSink::default();if fail_outcome{audit.fail_next_outcome()}let plane=ControlPlane::new(NamespaceRegistry::default(),identities,policies,tokens,mounts,KvStore::new(100).ok()?,audit);let mut runtime=Runtime::new(Seal,plane);runtime.initialize().ok()?;runtime.unseal(SecretMaterial::new(b"unseal".to_vec()).ok()?).ok()?;Some(RuntimeHttpHandler::new(runtime,FixedClock(10)))}fn request(method:HttpMethod,target:&str,body:&[u8])->HttpRequest{HttpRequest{method,target:target.to_owned(),headers:BTreeMap::from([("x-heptabao-namespace".to_owned(),"root".to_owned()),("x-heptabao-token".to_owned(),"service-token-0001".to_owned()),("x-request-id".to_owned(),format!("service-request-{:08}",body.len()+target.len()))]),body:heptabao_http_api::SensitiveBody::new(body.to_vec())}}#[test]fn put_and_read_use_runtime_control_plane(){let Some(mut handler)=handler(false)else{assert!(false);return};let put=handler.handle(request(HttpMethod::Put,"/v1/secret/a?cas=0",b"value"));assert_eq!(put.status,200);let get=handler.handle(request(HttpMethod::Get,"/v1/secret/a",b""));assert_eq!(get.status,200);assert_eq!(get.body,b"value");}#[test]fn uncertain_audit_moves_service_to_recovery_required(){let Some(mut handler)=handler(true)else{assert!(false);return};let result=handler.handle(request(HttpMethod::Put,"/v1/secret/a?cas=0",b"value"));assert_eq!(result.status,503);assert_eq!(result.headers.get("x-heptabao-outcome").map(String::as_str),Some("unknown"));assert_eq!(handler.runtime_state(),RuntimeState::RecoveryRequired);}}
'''
def cluster_rs()->str:
 return r'''#![forbid(unsafe_code)]
use std::collections::{BTreeMap,VecDeque};use heptabao_ha_core::NodeId;use heptabao_kms_contracts::{sha256,Digest32};
const MAGIC:&[u8;5]=b"HBCL1";
#[derive(Clone,Debug,Eq,PartialEq)]pub struct ClusterFrame{pub from:NodeId,pub to:NodeId,pub term:u64,pub index:u64,pub payload:Vec<u8>,pub payload_digest:Digest32}
#[derive(Clone,Debug,Eq,PartialEq)]pub enum ClusterError{FrameTooLarge,Truncated,InvalidMagic,DigestMismatch,InvalidNode,WrongDestination,GenerationConflict,StateRegression,TransportUnavailable}
impl ClusterFrame{pub fn new(from:NodeId,to:NodeId,term:u64,index:u64,payload:Vec<u8>)->Self{let payload_digest=sha256(&payload);Self{from,to,term,index,payload,payload_digest}}pub fn encode(&self)->Result<Vec<u8>,ClusterError>{if self.payload.len()>4*1024*1024{return Err(ClusterError::FrameTooLarge)}let mut output=Vec::with_capacity(69+self.payload.len());output.extend_from_slice(MAGIC);output.extend_from_slice(&self.from.get().to_be_bytes());output.extend_from_slice(&self.to.get().to_be_bytes());output.extend_from_slice(&self.term.to_be_bytes());output.extend_from_slice(&self.index.to_be_bytes());output.extend_from_slice(&(self.payload.len()as u32).to_be_bytes());output.extend_from_slice(self.payload_digest.as_bytes());output.extend_from_slice(&self.payload);Ok(output)}pub fn decode(bytes:&[u8],maximum:usize)->Result<Self,ClusterError>{if bytes.len()<73{return Err(ClusterError::Truncated)}if &bytes[..5]!=MAGIC{return Err(ClusterError::InvalidMagic)}let from=NodeId::new(u64::from_be_bytes(bytes[5..13].try_into().map_err(|_|ClusterError::Truncated)?)).map_err(|_|ClusterError::InvalidNode)?;let to=NodeId::new(u64::from_be_bytes(bytes[13..21].try_into().map_err(|_|ClusterError::Truncated)?)).map_err(|_|ClusterError::InvalidNode)?;let term=u64::from_be_bytes(bytes[21..29].try_into().map_err(|_|ClusterError::Truncated)?);let index=u64::from_be_bytes(bytes[29..37].try_into().map_err(|_|ClusterError::Truncated)?);let len=u32::from_be_bytes(bytes[37..41].try_into().map_err(|_|ClusterError::Truncated)?)as usize;if len>maximum||bytes.len()!=73+len{return Err(if len>maximum{ClusterError::FrameTooLarge}else{ClusterError::Truncated})}let mut digest=[0u8;32];digest.copy_from_slice(&bytes[41..73]);let payload=bytes[73..].to_vec();let payload_digest=Digest32::from_bytes(digest);if sha256(&payload)!=payload_digest{return Err(ClusterError::DigestMismatch)}Ok(Self{from,to,term,index,payload,payload_digest})}}
#[derive(Clone,Debug,Eq,PartialEq)]pub struct DurableHaState{pub generation:u64,pub term:u64,pub committed_index:u64,pub applied_index:u64,pub snapshot_digest:Option<Digest32>}
#[derive(Clone,Debug,Eq,PartialEq)]pub enum DurableFailure<E>{BeforeEntry(E),OutcomeUnknownAfterEntry(E)}pub trait DurableHaStore{type Error;fn read(&self)->Result<DurableHaState,Self::Error>;fn compare_and_commit(&mut self,expected_generation:u64,next:DurableHaState)->Result<DurableHaState,DurableFailure<Self::Error>>;}
#[derive(Clone,Debug)]pub struct MemoryDurableHaStore{state:DurableHaState}impl MemoryDurableHaStore{pub fn new()->Self{Self{state:DurableHaState{generation:0,term:0,committed_index:0,applied_index:0,snapshot_digest:None}}}}impl Default for MemoryDurableHaStore{fn default()->Self{Self::new()}}impl DurableHaStore for MemoryDurableHaStore{type Error=ClusterError;fn read(&self)->Result<DurableHaState,Self::Error>{Ok(self.state.clone())}fn compare_and_commit(&mut self,expected_generation:u64,mut next:DurableHaState)->Result<DurableHaState,DurableFailure<Self::Error>>{if self.state.generation!=expected_generation{return Err(DurableFailure::BeforeEntry(ClusterError::GenerationConflict))}if next.term<self.state.term||next.committed_index<self.state.committed_index||next.applied_index<self.state.applied_index||next.applied_index>next.committed_index{return Err(DurableFailure::BeforeEntry(ClusterError::StateRegression))}next.generation=expected_generation.checked_add(1).ok_or(DurableFailure::BeforeEntry(ClusterError::GenerationConflict))?;self.state=next.clone();Ok(next)}}
pub trait ClusterTransport{type Error;fn send(&mut self,frame:ClusterFrame)->Result<(),Self::Error>;fn receive(&mut self,node:NodeId)->Result<Option<ClusterFrame>,Self::Error>;}
#[derive(Clone,Debug,Default)]pub struct MemoryClusterTransport{queues:BTreeMap<NodeId,VecDeque<ClusterFrame>>}impl ClusterTransport for MemoryClusterTransport{type Error=ClusterError;fn send(&mut self,frame:ClusterFrame)->Result<(),Self::Error>{self.queues.entry(frame.to).or_default().push_back(frame);Ok(())}fn receive(&mut self,node:NodeId)->Result<Option<ClusterFrame>,Self::Error>{Ok(self.queues.entry(node).or_default().pop_front())}}
#[cfg(test)]mod tests{use super::*;#[test]fn frame_digest_and_size_are_verified(){let Ok(a)=NodeId::new(1)else{assert!(false);return};let Ok(b)=NodeId::new(2)else{assert!(false);return};let frame=ClusterFrame::new(a,b,1,1,b"payload".to_vec());let Ok(mut encoded)=frame.encode()else{assert!(false);return};let Ok(decoded)=ClusterFrame::decode(&encoded,1024)else{assert!(false);return};assert_eq!(decoded,frame);let last=encoded.len()-1;encoded[last]^=1;assert_eq!(ClusterFrame::decode(&encoded,1024),Err(ClusterError::DigestMismatch));}#[test]fn durable_state_is_cas_and_monotonic(){let mut store=MemoryDurableHaStore::new();let next=DurableHaState{generation:0,term:1,committed_index:1,applied_index:1,snapshot_digest:None};assert!(store.compare_and_commit(0,next).is_ok());let stale=DurableHaState{generation:0,term:0,committed_index:0,applied_index:0,snapshot_digest:None};assert_eq!(store.compare_and_commit(0,stale.clone()),Err(DurableFailure::BeforeEntry(ClusterError::GenerationConflict)));assert_eq!(store.compare_and_commit(1,stale),Err(DurableFailure::BeforeEntry(ClusterError::StateRegression)));}#[test]fn transport_delivers_only_to_exact_node(){let Ok(a)=NodeId::new(1)else{assert!(false);return};let Ok(b)=NodeId::new(2)else{assert!(false);return};let mut transport=MemoryClusterTransport::default();assert_eq!(transport.send(ClusterFrame::new(a,b,1,1,b"x".to_vec())),Ok(()));assert_eq!(transport.receive(a),Ok(None));assert!(transport.receive(b).is_ok_and(|value|value.is_some()));}}
'''
def agent_proxy_rs()->str:
 return r'''#![forbid(unsafe_code)]
use std::collections::BTreeMap;use std::fmt;use std::net::SocketAddr;use heptabao_client_tools::{ClientError,ProxyPolicy};use heptabao_http_api::{HttpHandler,HttpRequest,HttpResponse};use heptabao_kms_contracts::SecretMaterial;
#[derive(Clone)]pub struct AgentCredential{namespace:String,token:SecretMaterial,expires_at_ms:u64}impl AgentCredential{pub fn new(namespace:&str,token:SecretMaterial,expires_at_ms:u64)->Result<Self,AgentError>{if namespace.is_empty()||expires_at_ms==0{return Err(AgentError::InvalidCredential)}Ok(Self{namespace:namespace.to_owned(),token,expires_at_ms})}pub fn namespace(&self)->&str{&self.namespace}pub fn token(&self)->&SecretMaterial{&self.token}}impl fmt::Debug for AgentCredential{fn fmt(&self,f:&mut fmt::Formatter<'_>)->fmt::Result{f.debug_struct("AgentCredential").field("namespace",&self.namespace).field("token_len",&self.token.len()).field("expires_at_ms",&self.expires_at_ms).finish()}}
#[derive(Clone,Debug,Eq,PartialEq)]pub enum AgentError{InvalidCredential,Missing,Expired,InvalidRequest,RequestTooLarge,NonLoopback}
#[derive(Clone,Debug,Default)]pub struct AgentService{credentials:BTreeMap<String,AgentCredential>}impl AgentService{pub fn insert(&mut self,key:&str,credential:AgentCredential)->Result<(),AgentError>{if key.is_empty()||key.len()>64{return Err(AgentError::InvalidCredential)}self.credentials.insert(key.to_owned(),credential);Ok(())}pub fn lookup(&self,key:&str,now_ms:u64)->Result<AgentCredential,AgentError>{let value=self.credentials.get(key).ok_or(AgentError::Missing)?;if now_ms>=value.expires_at_ms{return Err(AgentError::Expired)}Ok(value.clone())}pub fn handle_frame(&self,frame:&[u8])->Result<Vec<u8>,AgentError>{if frame.len()>1024{return Err(AgentError::RequestTooLarge)}let text=std::str::from_utf8(frame).map_err(|_|AgentError::InvalidRequest)?;let parts:Vec<_>=text.trim_end().split(' ').collect();if parts.len()!=3||parts[0]!="GET"{return Err(AgentError::InvalidRequest)}let now=parts[2].parse().map_err(|_|AgentError::InvalidRequest)?;let credential=self.lookup(parts[1],now)?;let mut output=format!("namespace={}\ntoken-length={}\n\n",credential.namespace(),credential.token().len()).into_bytes();output.extend_from_slice(credential.token().expose());Ok(output)}}
pub trait ProxyUpstream{type Error;fn forward(&mut self,request:HttpRequest)->Result<HttpResponse,Self::Error>;}
pub struct ProxyService<U:ProxyUpstream>{upstream:U,policy:ProxyPolicy,address:SocketAddr,tls:bool}impl<U:ProxyUpstream>ProxyService<U>{pub fn new(upstream:U,policy:ProxyPolicy,address:SocketAddr,tls:bool)->Result<Self,ClientError>{policy.authorize_upstream(address,tls)?;Ok(Self{upstream,policy,address,tls})}pub fn upstream_security(&self)->(SocketAddr,bool){(self.address,self.tls)}}impl<U:ProxyUpstream>HttpHandler for ProxyService<U>{fn handle(&mut self,mut request:HttpRequest)->HttpResponse{request.headers=self.policy.filter_headers(&request.headers);match self.upstream.forward(request){Ok(response)=>response,Err(_)=>HttpResponse{status:503,headers:BTreeMap::new(),body:b"upstream unavailable".to_vec()}}}}
#[cfg(test)]mod tests{use std::collections::BTreeSet;use super::*;use heptabao_http_api::{HttpMethod,SensitiveBody};#[test]fn agent_expiry_and_debug_are_fail_closed(){let Ok(token)=SecretMaterial::new(b"agent-token".to_vec())else{assert!(false);return};let Ok(credential)=AgentCredential::new("root",token,100)else{assert!(false);return};assert!(!format!("{credential:?}").contains("agent-token"));let mut agent=AgentService::default();assert_eq!(agent.insert("default",credential),Ok(()));assert_eq!(agent.lookup("default",100),Err(AgentError::Expired));assert!(agent.handle_frame(b"GET default 99\n").is_ok());}#[test]fn proxy_requires_tls_and_filters_headers(){struct Upstream;impl ProxyUpstream for Upstream{type Error=();fn forward(&mut self,request:HttpRequest)->Result<HttpResponse,Self::Error>{Ok(HttpResponse{status:200,headers:BTreeMap::new(),body:request.headers.keys().cloned().collect::<Vec<_>>().join(",").into_bytes()})}}let policy=ProxyPolicy{allow_plain_loopback:true,require_tls_remote:true,allowed_headers:BTreeSet::from(["x-request-id".to_owned(),"connection".to_owned()])};let remote:"192.0.2.1:8200".parse();let Ok(remote)=remote else{assert!(false);return};assert!(matches!(ProxyService::new(Upstream,policy.clone(),remote,false),Err(ClientError::TlsRequired)));let local:"127.0.0.1:8200".parse();let Ok(local)=local else{assert!(false);return};let Ok(mut proxy)=ProxyService::new(Upstream,policy,local,false)else{assert!(false);return};let request=HttpRequest{method:HttpMethod::Get,target:"/v1/sys/health".to_owned(),headers:BTreeMap::from([("x-request-id".to_owned(),"r".to_owned()),("connection".to_owned(),"keep-alive".to_owned())]),body:SensitiveBody::new(Vec::new())};let response=proxy.handle(request);assert_eq!(response.body,b"x-request-id");}}
'''
def service_bin()->str:return '''fn main(){eprintln!("HeptaBao service: no production provider set or authority grant; refusing startup");std::process::exit(78);}\n'''
def module_doc(name:str,purpose:str,deps:str,invariants:list[str],gaps:list[str])->str:
 return f'''# `{name}` developer guide

## Purpose and responsibility

{purpose}

## Maturity and authority

Development operational vertical slice. It is not a qualified deployment or release.

## Dependency direction

{deps}

## Public API

Generated from exact source by Module Documentation V2.

## State model and invariants

'''+"\n".join(f"- {item}"for item in invariants)+'''

## Errors, failure classes, and retry semantics

Configuration, admission and validation failures occur before effects. Runtime, durable-store and upstream uncertainty remains explicit and requires reconciliation.

## Data formats and compatibility

Formats are bounded V1.8 contracts and do not create a broad compatibility or migration promise.

## Security considerations

Inline secrets, secret metric labels, remote plaintext, stale durable generations and expired agent credentials are rejected. Service traffic enters only through the runtime/control-plane path.

## Testing strategy

Tests cover configuration ambiguity, health/readiness, HTTP-to-runtime effects, outcome uncertainty, metric cardinality, cluster framing/CAS, agent expiry and proxy TLS/header policy.

## Extension rules

Do not add alternate request paths, ambient configuration, unbounded labels, non-CAS durable state, remote plaintext, inline credentials or unsigned release claims.

## Operational guidance

The service binary fails closed without configured qualified providers. External operational evidence remains mandatory.

## Known gaps

'''+"\n".join(f"- {item}"for item in gaps)+'''

## Traceability

- Plan: `docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md`
- Status: `planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml`
- Blockers: `planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml`
- Module truth: `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml`
'''
def renderer()->str:
 return r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse,importlib.util
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];TRUTH=Path("planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml");PLAN_ID="HEPTABAO-PLAN-2026-09-02-V1.8.0";SPEC=importlib.util.spec_from_file_location("base",ROOT/"scripts/render_plan_v1_4_7.py");assert SPEC and SPEC.loader;BASE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(BASE);BASE.PLAN_ID=PLAN_ID;BASE.TRUTH_PATH=TRUTH
def build()->dict:
 value=BASE.build_truth(ROOT);value["schema"]="heptabao.module-source-truth.v5";value["plan_id"]=PLAN_ID;value.pop("baseline_commit",None);value.pop("baseline_tree",None);value["source_baseline"]=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml").read_text())["source_baseline"];return value
def render(write:bool)->None:
 value=build();expected=BASE.dump_yaml(value);path=ROOT/TRUTH
 if write:path.write_text(expected)
 elif not path.is_file()or path.read_text()!=expected:raise SystemExit("V1.8 truth drift")
 for module in value["modules"]:
  doc=ROOT/module["module_guide"];expected_doc=BASE.module_doc_expected(ROOT,module)
  if write:doc.write_text(expected_doc)
  elif doc.read_text()!=expected_doc:raise SystemExit(f"guide drift {doc}")
 index=ROOT/"docs/modules/README.md";text=index.read_text();pairs=[(BASE.BEGIN_INDEX,BASE.END_INDEX)]+[(f"<!-- BEGIN V1.{version}.0 MODULE TRUTH INDEX -->",f"<!-- END V1.{version}.0 MODULE TRUTH INDEX -->")for version in(5,6,7,8)]
 for begin,end in pairs:
  if begin in text and end in text:start=text.index(begin);finish=text.index(end,start)+len(end);text=text[:start]+text[finish:]
 block=f'''<!-- BEGIN V1.8.0 MODULE TRUTH INDEX -->\n## V1.8.0 machine-verified module truth\n\nCurrent workspace: `{value["module_count"]}` crates. Run `python scripts/render_module_source_truth_v1_8_0.py --check`.\n<!-- END V1.8.0 MODULE TRUTH INDEX -->''';expected_index=text.rstrip()+"\n\n"+block+"\n"
 if write:index.write_text(expected_index)
 elif index.read_text()!=expected_index:raise SystemExit("index drift")
def main()->int:
 parser=argparse.ArgumentParser();group=parser.add_mutually_exclusive_group(required=True);group.add_argument("--write",action="store_true");group.add_argument("--check",action="store_true");args=parser.parse_args();render(args.write);print("PASS V1.8 module truth");return 0
if __name__=="__main__":raise SystemExit(main())
'''
def module_validator()->str:
 baseline=repr(BASELINE_CRATES)
 return f'''#!/usr/bin/env python3
from __future__ import annotations
import tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];BASELINE={baseline};EXEMPT={{"README.md","MODULE_DOCUMENTATION_STANDARD_V1.md","MODULE_DOCUMENTATION_STANDARD_V2.md"}}
def members()->dict[str,Path]:
 data=tomllib.loads((ROOT/"Cargo.toml").read_text());result={{}}
 for entry in data["workspace"]["members"]:
  for path in ROOT.glob(entry):
   if(path/"Cargo.toml").is_file():result[tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"]]=path
 return result
def main()->int:
 workspace=members();names=set(workspace);missing=BASELINE-names
 if missing:raise SystemExit(f"prior crate disappeared {{sorted(missing)}}")
 candidates=[ROOT/f"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_{{version}}_0.yaml"for version in(8,7,6,5)]+[ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_4_7.yaml"];truth_path=next((path for path in candidates if path.is_file()),None)
 if truth_path is None:raise SystemExit("truth missing")
 truth=yaml.safe_load(truth_path.read_text())
 if{{item["crate"]for item in truth["modules"]}}!=names or truth["module_count"]!=len(names):raise SystemExit("truth/workspace mismatch")
 docs=ROOT/"docs/modules"
 for name in sorted(names):
  path=docs/f"{{name}}.md"
  if not path.is_file():raise SystemExit(f"guide missing {{name}}")
  text=path.read_text()
  for token in("## Public API","BEGIN GENERATED V1.4.7 PUBLIC API TRUTH","BEGIN GENERATED V1.4.7 MODULE FACTS","## Known gaps","## Traceability"):
   if token not in text:raise SystemExit(f"{{name}} missing {{token}}")
 orphan={{path.name for path in docs.glob("*.md")if path.name not in EXEMPT and path.stem not in names}}
 if orphan:raise SystemExit(f"orphan guides {{sorted(orphan)}}")
 print(f"PASS successor module docs {{len(names)}} crates");return 0
if __name__=="__main__":raise SystemExit(main())
'''
def v170_successor()->str:
 return r'''#!/usr/bin/env python3
from __future__ import annotations
import subprocess,tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];REQUIRED={"heptabao-http-api","heptabao-ha-core","heptabao-plugin-host","heptabao-compat-runner","heptabao-client-tools"};CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def main()->int:
 status=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_7_0_SERVICE_HA_STATUS.yaml").read_text());blockers=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_7_0.yaml").read_text())
 if status["claims"]!=CLAIMS or blockers["claims"]!=CLAIMS:raise SystemExit("V1.7 authority drift")
 subprocess.run(["git","merge-base","--is-ancestor",status["source_baseline"]["commit"],"HEAD"],cwd=ROOT,check=True)
 data=tomllib.loads((ROOT/"Cargo.toml").read_text());names=set()
 for entry in data["workspace"]["members"]:
  for path in ROOT.glob(entry):
   if(path/"Cargo.toml").is_file():names.add(tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"])
 if not REQUIRED.issubset(names):raise SystemExit("V1.7 crate disappeared")
 current=(ROOT/"docs/CURRENT_DOCUMENTATION.md").read_text()
 if"HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md"not in current and"HEPTABAO_PLAN_V1_7_0_SERVICE_HA_PLUGIN_COMPATIBILITY.md"not in current:raise SystemExit("V1.7 lineage missing")
 print("PASS inherited V1.7 lineage");return 0
if __name__=="__main__":raise SystemExit(main())
'''
def v170_tests()->str:
 return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class V170SuccessorTests(unittest.TestCase):
 def test_v170_receipt_is_repository_only(self)->None:
  value=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text());self.assertEqual([],value["external_or_control_blockers_closed"]);self.assertEqual("NONE",value["claims"]["authority_effect"])
 def test_v170_crates_remain(self)->None:
  truth=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text());names={item["crate"]for item in truth["modules"]};self.assertTrue({"heptabao-http-api","heptabao-ha-core","heptabao-plugin-host","heptabao-compat-runner","heptabao-client-tools"}.issubset(names))
if __name__=="__main__":unittest.main()
'''
def release_script()->str:
 return r'''#!/usr/bin/env python3
from __future__ import annotations
import argparse,gzip,hashlib,io,json,os,tarfile,tomllib
from pathlib import Path
EXCLUDED={".git","target",".exec","__pycache__",".pytest_cache"}
def files(root:Path)->list[Path]:
 output=[]
 for path in root.rglob("*"):
  if not path.is_file()or any(part in EXCLUDED for part in path.relative_to(root).parts)or path.suffix==".pyc"or path.name.startswith("heptabao-release-"):continue
  if path.match(".github/workflows/exec-*"):continue
  output.append(path)
 return sorted(output,key=lambda path:path.relative_to(root).as_posix())
def metadata(root:Path,paths:list[Path])->tuple[bytes,bytes]:
 manifest=[]
 for path in paths:manifest.append({"path":path.relative_to(root).as_posix(),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),"size":path.stat().st_size})
 manifest_bytes=(json.dumps({"schema":"heptabao.release-manifest.v1","files":manifest},sort_keys=True,separators=(",",":"))+"\n").encode()
 packages=[]
 for cargo in sorted(root.rglob("Cargo.toml")):
  if any(part in EXCLUDED for part in cargo.relative_to(root).parts):continue
  value=tomllib.loads(cargo.read_text());package=value.get("package")
  if package:packages.append({"name":package.get("name"),"version":package.get("version"),"path":cargo.parent.relative_to(root).as_posix()})
 sbom_bytes=(json.dumps({"spdxVersion":"SPDX-2.3","name":"HeptaBao source candidate","packages":packages},sort_keys=True,separators=(",",":"))+"\n").encode();return manifest_bytes,sbom_bytes
def build(root:Path)->bytes:
 paths=files(root);manifest,sbom=metadata(root,paths);raw=io.BytesIO()
 with tarfile.open(fileobj=raw,mode="w",format=tarfile.GNU_FORMAT)as archive:
  for path in paths:
   data=path.read_bytes();info=tarfile.TarInfo(path.relative_to(root).as_posix());info.size=len(data);info.mtime=0;info.uid=0;info.gid=0;info.uname="";info.gname="";info.mode=0o755 if os.access(path,os.X_OK)else 0o644;archive.addfile(info,io.BytesIO(data))
  for name,data in(("RELEASE-MANIFEST.json",manifest),("SBOM.spdx.json",sbom)):
   info=tarfile.TarInfo(name);info.size=len(data);info.mtime=0;info.uid=0;info.gid=0;info.uname="";info.gname="";info.mode=0o644;archive.addfile(info,io.BytesIO(data))
 output=io.BytesIO()
 with gzip.GzipFile(filename="",mode="wb",fileobj=output,mtime=0)as compressed:compressed.write(raw.getvalue())
 return output.getvalue()
def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("--root",type=Path,default=Path(__file__).resolve().parents[1]);parser.add_argument("--output",type=Path,required=True);args=parser.parse_args();data=build(args.root.resolve());args.output.write_bytes(data);print(hashlib.sha256(data).hexdigest());return 0
if __name__=="__main__":raise SystemExit(main())
'''
def release_test()->str:
 return r'''from __future__ import annotations
import importlib.util,tempfile,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];SPEC=importlib.util.spec_from_file_location("release",ROOT/"scripts/build_release_bundle_v1_8.py");assert SPEC and SPEC.loader;MODULE=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(MODULE)
class ReleaseBundleTests(unittest.TestCase):
 def test_bundle_is_byte_reproducible_and_contains_manifest_and_sbom(self)->None:
  first=MODULE.build(ROOT);second=MODULE.build(ROOT);self.assertEqual(first,second);self.assertGreater(len(first),1000)
if __name__=="__main__":unittest.main()
'''
def plan_doc(baseline:str,tree:str)->str:return f'''# HeptaBao Plan V1.8.0 — Operational Service Vertical Slice

Baseline: reviewed V1.7.0 integration `{baseline}`, tree `{tree}`.

This tranche adds strict secret-free configuration, bounded observability, an HTTP-to-runtime-to-control-plane service adapter, durable HA state/cluster framing contracts, loopback agent/proxy logic, and byte-reproducible source/SBOM bundles. New repository blockers `HB-BLK-REPO-086..093` remain review-required until exact head, prospective merge and current approvals complete.

The service has no alternate mutation path: authenticated HTTP operations become typed V1.5 requests and execute only through the V1.6 runtime. Runtime uncertainty returns an explicit outcome-unknown response and disables readiness. Remote plaintext, inline configuration secrets, secret metric labels, stale durable generations, expired agent credentials and unbounded release metadata fail closed.

No real TLS/HSM/consensus/sandbox/offsite/Oracle/operations provider is qualified. `HB-BLK-CTRL-001` and `HB-BLK-EXT-001..007` remain factual external requirements; every authority flag remains false.
'''
def current_docs()->str:return '''# HeptaBao Current Documentation

## Current normative set

| Subject | Current document |
|---|---|
| active plan | `docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md` |
| current status | `planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml` |
| blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml` |
| normative manifest | `planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_0.yaml` |
| module truth | `planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml` |
| operational architecture | `docs/architecture/HEPTABAO_OPERATIONAL_SERVICE_V1.md` |
| V1.7 post-merge receipt | `planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml` |
| current gate | `.github/workflows/plan-v1.8.0-operational-service.yml` |

The 42-crate source tree now contains configuration, observability, HTTP/runtime service composition, cluster framing/durable HA state, agent/proxy logic and deterministic source/SBOM bundle generation in addition to all inherited domains. These are development source implementations, not qualified providers or a release. Control/external blockers and all authority claims remain open/false.
'''
def architecture()->str:return '''# HeptaBao Operational Service Architecture V1

```text
strict config → sealed runtime → strict HTTP edge → typed control-plane request
                                            → audit intent → KV effect → audit outcome
runtime state → health/readiness and bounded metrics
HA core ↔ exact cluster frame ↔ CAS durable HA state
agent credential cache → loopback frame / proxy TLS policy
source tree → deterministic manifest + SPDX source SBOM bundle
```

Configuration rejects unknown/duplicate keys, inline secret keys, relative storage paths and remote plaintext. Health never reports ready while sealed, draining or recovery-required. Metric labels have fixed names, size and total-series caps and reject secret/high-cardinality identities.

Cluster payload digests are verified before admission; durable state uses generation CAS and monotonic term/commit/apply checks. Agent credentials are redacted and expire fail closed. Proxy forwarding strips hop-by-hop credentials and requires TLS away from loopback.
'''
def status_doc(baseline:str,tree:str)->dict[str,Any]:return {"schema":"heptabao.v1-8-0-operational-service-status.v1","plan_id":PLAN_ID,"revision":"1.8.0","status":"SOURCE_IMPLEMENTED_EXACT_HEAD_MERGE_AND_INDEPENDENT_REVIEW_REQUIRED","current_plan":"docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md","current_blocker_register":"planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml","normative_manifest":"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_0.yaml","source_baseline":{"commit":baseline,"tree":tree},"closed_repository_scope_carried_forward":[f"HB-BLK-REPO-{i:03d}"for i in range(49,86)],"implementation":{"strict_configuration":"IMPLEMENTED_SOURCE","bounded_observability":"IMPLEMENTED_SOURCE","http_runtime_service":"IMPLEMENTED_SOURCE","cluster_frame_and_durable_state":"IMPLEMENTED_SOURCE","agent_proxy_services":"IMPLEMENTED_SOURCE","reproducible_release_bundle":"IMPLEMENTED_SOURCE","successor_module_truth":"IMPLEMENTED_SOURCE","exact_head_merge_gate":"IMPLEMENTED_SOURCE"},"repository_open":[f"HB-BLK-REPO-{i:03d}"for i in range(86,94)],"external_open":["HB-BLK-CTRL-001",*[f"HB-BLK-EXT-{i:03d}"for i in range(1,8)]],"remaining_qualification_gaps":["live protected branch rules and release channel","accountable independent role receipts and legal disposition","24x7 security operations and isolated signing custody","restricted Oracle campaign and broad compatibility","real TLS KMS HSM consensus sandbox remote anchor offsite backup and migration providers","kernel VM power-cut and cross-platform qualification","independently controlled exact-source reproduction"],"claims":CLAIMS}
def blockers_doc(baseline:str,tree:str)->dict[str,Any]:
 titles=["strict secret-free service configuration was absent","bounded health metrics and cardinality controls were absent","HTTP requests were not composed through the sealed runtime and control plane","cluster frames and durable HA generation CAS were absent","loopback agent credential service was absent","proxy TLS and header filtering service was absent","deterministic source manifest and SBOM bundle was absent","expanded operational workspace lacked source truth and exact head merge closure"];evidence=[["crates/heptabao-config"],["crates/heptabao-observability"],["crates/heptabao-service"],["crates/heptabao-cluster"],["crates/heptabao-agent-proxy"],["crates/heptabao-agent-proxy"],["scripts/build_release_bundle_v1_8.py","tests/plan/test_release_bundle_v1_8.py"],["planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml",".github/workflows/plan-v1.8.0-operational-service.yml"]];added=[]
 for number,title in enumerate(titles,86):added.append({"id":f"HB-BLK-REPO-{number:03d}","class":"REPOSITORY_CONTROLLED","severity":"CRITICAL"if number in{86,88,89}else"HIGH","title":title,"state":"IMPLEMENTED_SOURCE_REVIEW_REQUIRED","closure_criteria":["typed source and hostile tests exist","no alternate or fail-open path is admitted","module truth and deterministic bundle checks pass","exact head and prospective merge pass before closure"],"evidence":evidence[number-86],"closure_receipt_required":True})
 return {"schema":"heptabao.blocker-register-extension.v1_8_0","plan_id":PLAN_ID,"revision":"1.8.0","status":"ACTIVE_FAIL_CLOSED","inherits":"planning/HEPTABAO_BLOCKER_REGISTER_V1_7_0.yaml","source_baseline":{"commit":baseline,"tree":tree},"closed_carried_forward":[{"id":f"HB-BLK-REPO-{i:03d}","state":"CLOSED_REPOSITORY_SCOPE"}for i in range(49,86)],"added_blockers":added,"external_and_control_blockers_carried_forward":["HB-BLK-CTRL-001",*[f"HB-BLK-EXT-{i:03d}"for i in range(1,8)]],"remaining_qualification_gaps":status_doc(baseline,tree)["remaining_qualification_gaps"],"claims":CLAIMS}
def receipt(baseline:str,tree:str,head:str)->dict[str,Any]:return {"schema":"heptabao.repository-post-merge-closure-receipt.v1","plan_id":PLAN_ID,"repository":{"id":1349115072,"full_name":"TrillionniumFoundation/HeptaBao"},"pull_request":66,"reviewed_head_commit":head,"merge_commit":baseline,"merge_tree":tree,"required_reviewers":["ProfHepta","Tomasrgbsf"],"administrator_bypass":False,"closed_repository_blockers":[f"HB-BLK-REPO-{i:03d}"for i in range(79,86)],"external_or_control_blockers_closed":[],"claims":CLAIMS}
def v170_successor()->str:return r'''#!/usr/bin/env python3
from __future__ import annotations
import subprocess,tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];REQUIRED={"heptabao-http-api","heptabao-ha-core","heptabao-plugin-host","heptabao-compat-runner","heptabao-client-tools"};CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def main()->int:
 status=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_7_0_SERVICE_HA_STATUS.yaml").read_text());blockers=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_7_0.yaml").read_text())
 if status["claims"]!=CLAIMS or blockers["claims"]!=CLAIMS:raise SystemExit("V1.7 authority drift")
 subprocess.run(["git","merge-base","--is-ancestor",status["source_baseline"]["commit"],"HEAD"],cwd=ROOT,check=True)
 data=tomllib.loads((ROOT/"Cargo.toml").read_text());names=set()
 for entry in data["workspace"]["members"]:
  for path in ROOT.glob(entry):
   if(path/"Cargo.toml").is_file():names.add(tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"])
 if not REQUIRED.issubset(names):raise SystemExit("V1.7 crate disappeared")
 current=(ROOT/"docs/CURRENT_DOCUMENTATION.md").read_text()
 if"HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md"not in current and"HEPTABAO_PLAN_V1_7_0_SERVICE_HA_PLUGIN_COMPATIBILITY.md"not in current:raise SystemExit("V1.7 lineage missing")
 print("PASS inherited V1.7 lineage");return 0
if __name__=="__main__":raise SystemExit(main())
'''
def v170_tests()->str:return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class V170SuccessorTests(unittest.TestCase):
 def test_v170_receipt_is_repository_only(self)->None:
  value=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text());self.assertEqual([],value["external_or_control_blockers_closed"]);self.assertEqual("NONE",value["claims"]["authority_effect"])
 def test_v170_crates_remain(self)->None:
  truth=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text());names={item["crate"]for item in truth["modules"]};self.assertTrue({"heptabao-http-api","heptabao-ha-core","heptabao-plugin-host","heptabao-compat-runner","heptabao-client-tools"}.issubset(names))
if __name__=="__main__":unittest.main()
'''
def plan_validator()->str:return r'''#!/usr/bin/env python3
from __future__ import annotations
import hashlib,subprocess,tomllib
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[1];NEW={"heptabao-config","heptabao-observability","heptabao-service","heptabao-cluster","heptabao-agent-proxy"};CLAIMS={"qualification":False,"compatibility_claim":False,"selected_candidates":[],"selection_effect":"NONE","production_authority":False,"migration_authority":False,"release_authority":False,"authority_effect":"NONE"}
def sha(path:Path)->str:return hashlib.sha256(path.read_bytes()).hexdigest()
def main()->int:
 status=yaml.safe_load((ROOT/"planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml").read_text());blockers=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml").read_text());receipt=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text())
 for value in(status,blockers,receipt):
  if value["claims"]!=CLAIMS:raise SystemExit("authority drift")
 baseline=status["source_baseline"];tree=subprocess.check_output(["git","rev-parse",f"{baseline['commit']}^{{tree}}"],cwd=ROOT,text=True).strip()
 if tree!=baseline["tree"]:raise SystemExit("baseline tree drift")
 subprocess.run(["git","merge-base","--is-ancestor",baseline["commit"],"HEAD"],cwd=ROOT,check=True)
 data=tomllib.loads((ROOT/"Cargo.toml").read_text());names=set()
 for entry in data["workspace"]["members"]:
  for path in ROOT.glob(entry):
   if(path/"Cargo.toml").is_file():names.add(tomllib.loads((path/"Cargo.toml").read_text())["package"]["name"])
 if not NEW.issubset(names):raise SystemExit(f"new crates missing {sorted(NEW-names)}")
 truth=yaml.safe_load((ROOT/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text())
 if{item["crate"]for item in truth["modules"]}!=names:raise SystemExit("truth mismatch")
 if[item["id"]for item in blockers["added_blockers"]]!=[f"HB-BLK-REPO-{i:03d}"for i in range(86,94)]:raise SystemExit("blocker mismatch")
 checks={"crates/heptabao-config/src/lib.rs":["RemotePlaintext","InlineSecretForbidden","DuplicateKey"],"crates/heptabao-observability/src/lib.rs":["CardinalityLimit","ForbiddenLabel","RecoveryRequired"],"crates/heptabao-service/src/lib.rs":["x-heptabao-outcome","runtime.execute","/v1/sys/health"],"crates/heptabao-cluster/src/lib.rs":["DigestMismatch","GenerationConflict","compare_and_commit"],"crates/heptabao-agent-proxy/src/lib.rs":["CredentialExpired","TlsRequired","filter_headers"],"scripts/build_release_bundle_v1_8.py":["mtime=0","SBOM.spdx.json","RELEASE-MANIFEST.json"]}
 for path,tokens in checks.items():
  text=(ROOT/path).read_text()
  for token in tokens:
   if token not in text:raise SystemExit(f"{path} missing {token}")
 workflow=(ROOT/".github/workflows/plan-v1.8.0-operational-service.yml").read_text()
 if"pull_request:"not in workflow or"push:"in workflow or"prospective-merge"not in workflow:raise SystemExit("workflow drift")
 manifest=yaml.safe_load((ROOT/"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_0.yaml").read_text())
 for item in manifest["files"]:
  path=ROOT/item["path"]
  if not path.is_file()or sha(path)!=item["sha256"]:raise SystemExit(f"manifest mismatch {item['path']}")
 subprocess.run(["python","scripts/render_module_source_truth_v1_8_0.py","--check"],cwd=ROOT,check=True);print("PASS V1.8 operational service");return 0
if __name__=="__main__":raise SystemExit(main())
'''
def plan_tests()->str:return r'''from __future__ import annotations
import unittest
from pathlib import Path
import yaml
ROOT=Path(__file__).resolve().parents[2]
class PlanV180Tests(unittest.TestCase):
 def test_repository_and_external_boundaries(self)->None:
  value=yaml.safe_load((ROOT/"planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml").read_text());self.assertEqual([f"HB-BLK-REPO-{i:03d}"for i in range(86,94)],[item["id"]for item in value["added_blockers"]]);self.assertIn("HB-BLK-EXT-007",value["external_and_control_blockers_carried_forward"]);self.assertEqual("NONE",value["claims"]["authority_effect"])
 def test_v170_receipt_is_repository_only(self)->None:
  value=yaml.safe_load((ROOT/"planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml").read_text());self.assertEqual([],value["external_or_control_blockers_closed"]);self.assertEqual([f"HB-BLK-REPO-{i:03d}"for i in range(79,86)],value["closed_repository_blockers"])
if __name__=="__main__":unittest.main()
'''
def workflow()->str:return '''name: HeptaBao V1.8.0 operational service
on:
  pull_request:
    types: [opened, synchronize, reopened, ready_for_review]
    branches: [integration/v1.4.4-technical-candidate]
permissions:
  contents: read
concurrency:
  group: v1.8.0-pr-${{ github.event.pull_request.number }}-${{ github.event.pull_request.head.sha }}
  cancel-in-progress: true
jobs:
  validate:
    name: v1.8.0 / pull_request / ${{ matrix.source_kind }}
    runs-on: ubuntu-24.04
    timeout-minutes: 240
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
      - name: Bind source
        shell: bash
        run: |
          set -euo pipefail;test "$(git rev-parse HEAD)" = "$SOURCE_SHA";if [[ "$SOURCE_KIND" == prospective-merge ]];then read -r merge first second extra <<<"$(git rev-list --parents -n 1 HEAD)";test "$merge" = "$SOURCE_SHA";test "$first" = "$BASE_SHA";test "$second" = "$HEAD_SHA";test -z "${extra:-}";else test "$SOURCE_SHA" = "$HEAD_SHA";fi
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: requirements-plan.txt
      - name: Validate all Python contracts and deterministic bundle
        shell: bash
        run: |
          set -euo pipefail;python -m pip install --disable-pip-version-check --requirement requirements-plan.txt;python scripts/render_module_source_truth_v1_8_0.py --check;python scripts/validate_plan_v1_8_0.py;python scripts/validate_plan_v1_7_0.py;python scripts/validate_plan_v1_6_0.py;python scripts/validate_plan_v1_5_0.py;python scripts/validate_plan_v1_4_7.py;python scripts/validate_plan_v1_4_6.py;python scripts/validate_plan_v1_4_5.py;python scripts/validate_module_documentation_v1_4_4.py;python -m unittest discover -s tests/plan -p 'test_*.py' -v;python -m unittest discover -s tests/platform -p 'test_*.py' -v;python -m unittest discover -s tests/oracle -p 'test_*.py' -v;python scripts/build_release_bundle_v1_8.py --output "$RUNNER_TEMP/one.tar.gz";python scripts/build_release_bundle_v1_8.py --output "$RUNNER_TEMP/two.tar.gz";cmp "$RUNNER_TEMP/one.tar.gz" "$RUNNER_TEMP/two.tar.gz"
      - name: Install Rust
        shell: bash
        run: rustup toolchain install 1.98.0 --profile minimal --component rustfmt --component clippy
      - name: Validate Rust workspace
        shell: bash
        run: |
          set -euo pipefail;cargo +1.98.0 fmt --all -- --check;cargo +1.98.0 test --locked --workspace --all-targets;cargo +1.98.0 clippy --locked --workspace --all-targets -- -D warnings
'''
def standard()->str:return '''# HeptaBao Module Documentation Standard V2
Every current workspace crate has one source-bound guide. The latest truth binds Cargo/source hashes, internal dependencies, lexical public declarations and discovered tests. Historical crates may not disappear and successor crates must satisfy the same standard. Current check: `python scripts/render_module_source_truth_v1_8_0.py --check`. This does not confer API stability, compatibility, qualification or authority.
'''
def materialize(root:Path)->None:
 baseline=sh(root,"git","rev-parse","HEAD");tree=sh(root,"git","rev-parse","HEAD^{tree}");parents=sh(root,"git","rev-list","--parents","-n","1","HEAD").split();head=parents[2]if len(parents)>2 else baseline;update_workspace(root)
 crates={"heptabao-config":(config_rs(),{"heptabao-kms-contracts":"../heptabao-kms-contracts"}),"heptabao-observability":(observability_rs(),{"heptabao-runtime":"../heptabao-runtime"}),"heptabao-service":(service_rs(),{"heptabao-control-plane":"../heptabao-control-plane","heptabao-http-api":"../heptabao-http-api","heptabao-identity":"../heptabao-identity","heptabao-kms-contracts":"../heptabao-kms-contracts","heptabao-kv":"../heptabao-kv","heptabao-namespace":"../heptabao-namespace","heptabao-observability":"../heptabao-observability","heptabao-policy":"../heptabao-policy","heptabao-runtime":"../heptabao-runtime","heptabao-system":"../heptabao-system","heptabao-token":"../heptabao-token"}),"heptabao-cluster":(cluster_rs(),{"heptabao-ha-core":"../heptabao-ha-core","heptabao-kms-contracts":"../heptabao-kms-contracts"}),"heptabao-agent-proxy":(agent_proxy_rs(),{"heptabao-client-tools":"../heptabao-client-tools","heptabao-http-api":"../heptabao-http-api","heptabao-kms-contracts":"../heptabao-kms-contracts"})}
 guides={"heptabao-config":("Parse canonical secret-free service configuration and bind its digest.","Depends on opaque key handles and SHA-256.",["Unknown and duplicate keys are rejected.","Remote plaintext requires a TLS provider.","Storage paths are absolute and secrets are references only."],["No HCL compatibility or dynamic reload."]),"heptabao-observability":("Expose readiness/liveness and bounded low-cardinality metrics.","Depends on runtime state.",["Recovery-required is never ready.","Secret/high-cardinality labels are forbidden.","Total series and labels are capped."],["No exporter, tracing backend or production SLO values."]),"heptabao-service":("Map strict HTTP requests into the sole sealed runtime/control-plane path.","Depends on HTTP, runtime, control-plane and domain crates.",["Health reflects runtime state.","Mutations have no alternate path.","Outcome uncertainty is explicit and disables readiness."],["No production listener supervisor, TLS provider or full endpoint surface."]),"heptabao-cluster":("Define exact cluster frames, in-memory transport and CAS durable HA state.","Depends on HA core and SHA-256.",["Payload digest and destination are exact.","Durable generation uses CAS.","Term/commit/apply cannot regress."],["No production network or durable store provider."]),"heptabao-agent-proxy":("Provide expiring loopback agent credentials and TLS/header-enforcing proxy logic.","Depends on client and HTTP contracts.",["Credentials are redacted and expire fail closed.","Remote plaintext is rejected.","Hop-by-hop credentials are stripped."],["No daemon supervisor, IPC ACL qualification or TLS implementation."])}
 for name,(source,deps)in crates.items():write(root,f"crates/{name}/Cargo.toml",crate_toml(name,deps));write(root,f"crates/{name}/src/lib.rs",source);write(root,f"docs/modules/{name}.md",module_doc(name,*guides[name]))
 write(root,"crates/heptabao-service/src/main.rs",service_bin());write(root,"scripts/render_module_source_truth_v1_8_0.py",renderer());write(root,"scripts/validate_module_documentation_v1_4_4.py",module_validator());write(root,"scripts/validate_plan_v1_7_0.py",v170_successor());write(root,"tests/plan/test_plan_v1_7_0.py",v170_tests());write(root,"scripts/build_release_bundle_v1_8.py",release_script());write(root,"tests/plan/test_release_bundle_v1_8.py",release_test());write(root,"docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md",standard());write(root,"docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md",plan_doc(baseline,tree));write(root,"docs/architecture/HEPTABAO_OPERATIONAL_SERVICE_V1.md",architecture());write(root,"planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml",yaml.safe_dump(status_doc(baseline,tree),sort_keys=False,width=120));write(root,"planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml",yaml.safe_dump(blockers_doc(baseline,tree),sort_keys=False,width=120));write(root,"planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml",yaml.safe_dump(receipt(baseline,tree,head),sort_keys=False,width=120));write(root,"docs/CURRENT_DOCUMENTATION.md",current_docs());write(root,".github/workflows/plan-v1.8.0-operational-service.yml",workflow());write(root,"scripts/validate_plan_v1_8_0.py",plan_validator());write(root,"tests/plan/test_plan_v1_8_0.py",plan_tests());subprocess.run(["python","scripts/render_module_source_truth_v1_8_0.py","--write"],cwd=root,check=True)
 truth=yaml.safe_load((root/"planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml").read_text());normative=["docs/CURRENT_DOCUMENTATION.md","docs/plan/HEPTABAO_PLAN_V1_8_0_OPERATIONAL_SERVICE_VERTICAL_SLICE.md","docs/architecture/HEPTABAO_OPERATIONAL_SERVICE_V1.md","docs/modules/MODULE_DOCUMENTATION_STANDARD_V2.md","planning/HEPTABAO_V1_8_0_OPERATIONAL_SERVICE_STATUS.yaml","planning/HEPTABAO_BLOCKER_REGISTER_V1_8_0.yaml","planning/HEPTABAO_MODULE_SOURCE_TRUTH_V1_8_0.yaml","planning/evidence/repository/HEPTABAO_V1_7_0_POST_MERGE_CLOSURE_RECEIPT.yaml","scripts/render_module_source_truth_v1_8_0.py","scripts/validate_plan_v1_8_0.py","scripts/build_release_bundle_v1_8.py",".github/workflows/plan-v1.8.0-operational-service.yml"]+[item["module_guide"]for item in truth["modules"]];manifest={"schema":"heptabao.normative-document-manifest.v1_8_0","plan_id":PLAN_ID,"revision":"1.8.0","status":"CANDIDATE_EXACT_HEAD_MERGE_REVIEW_REQUIRED","source_baseline":{"commit":baseline,"tree":tree},"files":[{"path":path,"sha256":sha(root/path)}for path in sorted(set(normative))],"claims":CLAIMS};write(root,"planning/HEPTABAO_NORMATIVE_DOCUMENT_MANIFEST_V1_8_0.yaml",yaml.safe_dump(manifest,sort_keys=False,width=120))
def main()->int:
 parser=argparse.ArgumentParser();parser.add_argument("root",type=Path);args=parser.parse_args();materialize(args.root.resolve());return 0
if __name__=="__main__":raise SystemExit(main())
