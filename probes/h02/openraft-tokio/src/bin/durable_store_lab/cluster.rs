use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;

use openraft::async_runtime::WatchReceiver;
use openraft::errors::decompose::DecomposeResult;
use openraft::{Config, ReadPolicy, SnapshotPolicy};
use openraft_memstore::{ClientRequest, MemStoreStateMachine, TypeConfig};
use tokio::task::spawn_blocking;
use tokio::time::{sleep, timeout};

use super::network::{DurableNetworkFactory, DurableRaft, DurableRouter};
use super::store::{DurableLogStore, DurableStateMachine};

pub type AnyResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

pub struct DurableNode {
    pub raft: DurableRaft,
    pub log_store: Arc<DurableLogStore>,
    pub state_machine: Arc<DurableStateMachine>,
}

pub struct DurableCluster {
    root: PathBuf,
    router: DurableRouter,
    config: Arc<Config>,
    nodes: BTreeMap<u64, DurableNode>,
}

impl DurableCluster {
    pub fn new(root: impl AsRef<Path>) -> AnyResult<Self> {
        let root = root.as_ref().to_path_buf();
        fs::create_dir_all(&root)?;
        let config = Config {
            heartbeat_interval: 40,
            election_timeout_min: 120,
            election_timeout_max: 240,
            snapshot_policy: SnapshotPolicy::LogsSinceLast(3),
            max_in_snapshot_log_to_keep: 0,
            enable_pre_vote: Some(true),
            ..Config::default()
        }
        .validate()?;
        Ok(Self {
            root,
            router: DurableRouter::default(),
            config: Arc::new(config),
            nodes: BTreeMap::new(),
        })
    }

    fn node_root(&self, id: u64) -> PathBuf {
        self.root.join(format!("node-{id}"))
    }

    async fn open_stores(
        root: PathBuf,
    ) -> AnyResult<(Arc<DurableLogStore>, Arc<DurableStateMachine>)> {
        spawn_blocking(move || {
            let log_store = DurableLogStore::open(root.join("log"))?;
            let state_machine = DurableStateMachine::open(root.join("state-machine"))?;
            Ok::<_, std::io::Error>((log_store, state_machine))
        })
        .await??
        .pipe(Ok)
    }

    pub async fn start_node(&mut self, id: u64) -> AnyResult<()> {
        if self.nodes.contains_key(&id) {
            return Err(format!("node {id} is already started").into());
        }
        let (log_store, state_machine) = Self::open_stores(self.node_root(id)).await?;
        let network = DurableNetworkFactory::new(id, self.router.clone());
        let raft = DurableRaft::new(
            id,
            self.config.clone(),
            network,
            log_store.clone(),
            state_machine.clone(),
        )
        .await?;
        self.router.register(id, raft.clone()).await;
        self.nodes.insert(
            id,
            DurableNode {
                raft,
                log_store,
                state_machine,
            },
        );
        Ok(())
    }

    pub async fn bootstrap_three_voters(&mut self) -> AnyResult<()> {
        self.start_node(1).await?;
        self.nodes[&1]
            .raft
            .initialize(BTreeMap::from([(1_u64, ())]))
            .await
            .decompose()
            .unwrap()?;
        self.nodes[&1]
            .raft
            .wait(Some(Duration::from_secs(8)))
            .current_leader(1, "durable single-node initialization")
            .await?;

        for id in [2_u64, 3] {
            self.start_node(id).await?;
            self.nodes[&1]
                .raft
                .add_learner(id, (), true)
                .await
                .decompose()
                .unwrap()?;
        }

        self.nodes[&1]
            .raft
            .change_membership(BTreeSet::from([1_u64, 2, 3]), false)
            .await
            .decompose()
            .unwrap()?;
        for node in self.nodes.values() {
            node.raft
                .wait(Some(Duration::from_secs(8)))
                .voter_ids([1_u64, 2, 3], "durable three-voter membership")
                .await?;
        }
        Ok(())
    }

    pub async fn reopen_three_voters(&mut self) -> AnyResult<u64> {
        for id in [1_u64, 2, 3] {
            self.start_node(id).await?;
        }
        let leader = self.consensus_leader().await?;
        for node in self.nodes.values() {
            node.raft
                .wait_for_recovery(Some(Duration::from_secs(12)))
                .await?;
        }
        Ok(leader)
    }

    pub async fn consensus_leader(&self) -> AnyResult<u64> {
        timeout(Duration::from_secs(12), async {
            loop {
                let mut leaders = BTreeSet::new();
                for node in self.nodes.values() {
                    if let Some(leader) = node.raft.current_leader().await {
                        leaders.insert(leader);
                    }
                }
                if leaders.len() == 1 {
                    let leader = *leaders.iter().next().expect("one durable leader");
                    if self.nodes.contains_key(&leader) {
                        return leader;
                    }
                }
                sleep(Duration::from_millis(25)).await;
            }
        })
        .await
        .map_err(Into::into)
    }

    pub async fn write(&self, leader: u64, serial: u64, status: String) -> AnyResult<u64> {
        let response = self.nodes[&leader]
            .raft
            .client_write(ClientRequest {
                client: "heptabao-h02-durable".to_owned(),
                serial,
                status,
            })
            .await
            .decompose()
            .unwrap()?;
        Ok(response.log_id.index)
    }

    pub async fn wait_all_applied(&self, index: u64) -> AnyResult<()> {
        for node in self.nodes.values() {
            node.raft
                .wait(Some(Duration::from_secs(12)))
                .applied_index_at_least(Some(index), "durable state replication")
                .await?;
        }
        Ok(())
    }

    pub async fn read_index(&self, leader: u64) -> AnyResult<()> {
        self.nodes[&leader]
            .raft
            .ensure_linearizable(ReadPolicy::ReadIndex)
            .await
            .decompose()
            .unwrap()?;
        Ok(())
    }

    pub async fn trigger_snapshot(&self, leader: u64, minimum_index: u64) -> AnyResult<()> {
        self.nodes[&leader].raft.trigger().snapshot().await?;
        self.nodes[&leader]
            .raft
            .wait(Some(Duration::from_secs(12)))
            .metrics(
                |metrics| {
                    metrics
                        .snapshot
                        .as_ref()
                        .is_some_and(|log_id| log_id.index >= minimum_index)
                },
                "durable snapshot contains committed writes",
            )
            .await?;
        let snapshot_path = self.nodes[&leader].state_machine.snapshot_path();
        if !snapshot_path.is_file() || fs::metadata(snapshot_path)?.len() == 0 {
            return Err(format!(
                "snapshot was not durably published: {}",
                snapshot_path.display()
            )
            .into());
        }
        Ok(())
    }

    pub async fn state(&self, id: u64) -> MemStoreStateMachine {
        self.nodes[&id].state_machine.get_state_machine().await
    }

    pub async fn all_states_equal(&self) -> bool {
        let baseline = self.state(1).await;
        for id in [2_u64, 3] {
            let state = self.state(id).await;
            if state.last_applied_log != baseline.last_applied_log
                || state.client_status != baseline.client_status
            {
                return false;
            }
        }
        true
    }

    pub fn artifact_paths(&self) -> BTreeMap<String, PathBuf> {
        let mut result = BTreeMap::new();
        for (id, node) in &self.nodes {
            result.insert(
                format!("node-{id}-log"),
                node.log_store.state_path().to_path_buf(),
            );
            result.insert(
                format!("node-{id}-state"),
                node.state_machine.state_path().to_path_buf(),
            );
            result.insert(
                format!("node-{id}-snapshot"),
                node.state_machine.snapshot_path().to_path_buf(),
            );
        }
        result
    }

    pub async fn rpc_counts(&self) -> BTreeMap<String, u64> {
        self.router.rpc_counts().await
    }

    pub async fn exercise_partition(&self, leader: u64) -> AnyResult<(bool, bool)> {
        let before = self.nodes[&leader]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();
        self.router.isolate(leader).await;
        self.router.pause(leader).await;
        let result = timeout(
            Duration::from_millis(700),
            self.nodes[&leader].raft.client_write(ClientRequest {
                client: "heptabao-h02-durable".to_owned(),
                serial: 999_001,
                status: "isolated-writer-must-not-commit".to_owned(),
            }),
        )
        .await;
        let rejected = !matches!(result, Ok(Ok(_)));
        sleep(Duration::from_millis(300)).await;
        let after = self.nodes[&leader]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();
        self.router.resume(leader).await;
        self.router.heal_all().await;
        Ok((rejected, after <= before))
    }

    pub async fn shutdown(mut self) -> AnyResult<()> {
        let ids = self.nodes.keys().copied().collect::<Vec<_>>();
        for id in ids {
            if let Some(node) = self.nodes.remove(&id) {
                self.router.unregister(id).await;
                node.raft.shutdown().await?;
            }
        }
        Ok(())
    }
}

trait Pipe: Sized {
    fn pipe<T>(self, f: impl FnOnce(Self) -> T) -> T {
        f(self)
    }
}

impl<T> Pipe for T {}
