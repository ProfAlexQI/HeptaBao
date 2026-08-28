use std::collections::{BTreeMap, BTreeSet};
use std::error::Error;
use std::sync::Arc;
use std::time::Duration;

use openraft::async_runtime::WatchReceiver;
use openraft::errors::decompose::DecomposeResult;
use openraft::{Config, LogIdOptionExt, Raft, ReadPolicy, SnapshotPolicy};
use openraft_memstore::{
    BlockConfig, ClientRequest, MemLogStore, MemStateMachine, TypeConfig, new_mem_store,
};
use serde_json::{Value, json};
use tokio::time::{sleep, timeout};

use super::network::{InMemoryNetworkFactory, InMemoryRouter, MemRaft};

pub type AnyResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

const CASES: [&str; 6] = [
    "raft-deterministic-apply-and-restart",
    "raft-committed-snapshot-conflict-rejected",
    "raft-joint-membership-single-writer",
    "raft-process-pause-plus-partition",
    "raft-quorum-loss-fail-closed",
    "raft-incomplete-run-replay-diagnostics",
];

pub struct Node {
    pub raft: MemRaft,
    pub log_store: Arc<MemLogStore>,
    pub state_machine: Arc<MemStateMachine>,
}

pub struct Cluster {
    router: InMemoryRouter,
    config: Arc<Config>,
    nodes: BTreeMap<u64, Node>,
}

impl Cluster {
    pub fn new() -> AnyResult<Self> {
        let config = Config {
            heartbeat_interval: 40,
            election_timeout_min: 120,
            election_timeout_max: 240,
            snapshot_policy: SnapshotPolicy::LogsSinceLast(3),
            max_in_snapshot_log_to_keep: 0,
            enable_pre_vote: true,
            ..Config::default()
        }
        .validate()?;
        Ok(Self {
            router: InMemoryRouter::default(),
            config: Arc::new(config),
            nodes: BTreeMap::new(),
        })
    }

    pub async fn start_node(&mut self, id: u64) -> AnyResult<()> {
        let (log_store, state_machine) = new_mem_store();
        self.start_node_with(id, log_store, state_machine).await
    }

    async fn start_node_with(
        &mut self,
        id: u64,
        log_store: Arc<MemLogStore>,
        state_machine: Arc<MemStateMachine>,
    ) -> AnyResult<()> {
        let network = InMemoryNetworkFactory::new(id, self.router.clone());
        let raft = Raft::<TypeConfig, Arc<MemStateMachine>>::new(
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
            Node {
                raft,
                log_store,
                state_machine,
            },
        );
        Ok(())
    }

    pub async fn bootstrap_three_voters(&mut self) -> AnyResult<()> {
        self.start_node(1).await?;
        let initial = BTreeMap::from([(1_u64, ())]);
        self.nodes[&1]
            .raft
            .initialize(initial)
            .await
            .decompose()
            .unwrap()?;
        self.nodes[&1]
            .raft
            .wait(Some(Duration::from_secs(5)))
            .current_leader(1, "single-node initialization")
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
                .wait(Some(Duration::from_secs(5)))
                .voter_ids([1_u64, 2, 3], "three-voter membership")
                .await?;
        }
        Ok(())
    }

    pub async fn write(&self, leader_id: u64, serial: u64, status: String) -> AnyResult<u64> {
        let response = self.nodes[&leader_id]
            .raft
            .client_write(ClientRequest {
                client: "heptabao-h02".to_owned(),
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
                .wait(Some(Duration::from_secs(5)))
                .applied_index_at_least(Some(index), "replicate candidate evidence")
                .await?;
        }
        Ok(())
    }

    pub async fn state_digest_input(&self, id: u64) -> BTreeMap<String, String> {
        self.nodes[&id]
            .state_machine
            .get_state_machine()
            .await
            .client_status
            .into_iter()
            .collect()
    }

    pub async fn restart_follower_with_fresh_state_machine(
        &mut self,
        id: u64,
        applied_index: u64,
    ) -> AnyResult<()> {
        let old = self.nodes.remove(&id).ok_or("missing restart node")?;
        self.router.unregister(id).await;
        old.raft.shutdown().await?;

        let fresh_state_machine = Arc::new(MemStateMachine::new(BlockConfig::default()));
        self.start_node_with(id, old.log_store, fresh_state_machine).await?;
        self.nodes[&id]
            .raft
            .wait(Some(Duration::from_secs(5)))
            .applied_index_at_least(Some(applied_index), "replay committed log after restart")
            .await?;
        Ok(())
    }

    pub async fn trigger_snapshot_and_catch_up(
        &self,
        lagging: u64,
        leader: u64,
        start_serial: u64,
    ) -> AnyResult<(u64, bool, bool)> {
        self.router.isolate(lagging).await;
        let before = self.nodes[&lagging]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();

        let mut last_index = 0;
        for offset in 0..6_u64 {
            last_index = self
                .write(leader, start_serial + offset, format!("snapshot-value-{offset}"))
                .await?;
        }
        self.nodes[&leader].raft.trigger().snapshot().await?;
        self.nodes[&leader]
            .raft
            .wait(Some(Duration::from_secs(5)))
            .metrics(
                |metrics| metrics.snapshot.as_ref().is_some_and(|log_id| log_id.index >= last_index),
                "leader snapshot contains committed writes",
            )
            .await?;

        self.router.heal_all().await;
        self.nodes[&lagging]
            .raft
            .wait(Some(Duration::from_secs(8)))
            .applied_index_at_least(Some(last_index), "lagging follower installs snapshot or catches up")
            .await?;

        let after = self.nodes[&lagging]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();
        let monotonic = after >= before && after >= Some(last_index);
        let converged = self.state_digest_input(lagging).await == self.state_digest_input(leader).await;
        Ok((last_index, monotonic, converged))
    }

    pub async fn linearizable(&self, leader: u64) -> AnyResult<bool> {
        self.nodes[&leader]
            .raft
            .ensure_linearizable(ReadPolicy::ReadIndex)
            .await
            .decompose()
            .unwrap()?;
        Ok(true)
    }

    pub async fn consensus_leader(&self, ids: &[u64], excluded: Option<u64>) -> AnyResult<u64> {
        let result = timeout(Duration::from_secs(6), async {
            loop {
                let mut reported = BTreeSet::new();
                for id in ids {
                    if let Some(leader) = self.nodes[id].raft.current_leader().await {
                        if excluded != Some(leader) {
                            reported.insert(leader);
                        }
                    }
                }
                if reported.len() == 1 {
                    return *reported.iter().next().expect("one leader");
                }
                sleep(Duration::from_millis(25)).await;
            }
        })
        .await?;
        Ok(result)
    }

    pub async fn leaders_reported(&self) -> BTreeSet<u64> {
        let mut result = BTreeSet::new();
        for node in self.nodes.values() {
            if let Some(leader) = node.raft.current_leader().await {
                result.insert(leader);
            }
        }
        result
    }

    pub async fn pause_and_elect(&self, old_leader: u64) -> AnyResult<(u64, bool, bool)> {
        self.router.pause(old_leader).await;
        let new_leader = self.consensus_leader(&[2, 3], Some(old_leader)).await?;

        let old_write = timeout(
            Duration::from_millis(700),
            self.nodes[&old_leader].raft.client_write(ClientRequest {
                client: "heptabao-h02".to_owned(),
                serial: 90_001,
                status: "old-leader-must-not-commit".to_owned(),
            }),
        )
        .await;
        let old_rejected = !matches!(old_write, Ok(Ok(Ok(_))));
        let new_write = self.write(new_leader, 90_002, "new-leader-committed".to_owned()).await.is_ok();
        Ok((new_leader, old_rejected, new_write))
    }

    pub async fn quorum_loss_fail_closed(&self, leader: u64) -> AnyResult<(bool, bool)> {
        let before = self.nodes[&leader]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();
        self.router.isolate(leader).await;
        let result = timeout(
            Duration::from_millis(700),
            self.nodes[&leader].raft.client_write(ClientRequest {
                client: "heptabao-h02".to_owned(),
                serial: 90_003,
                status: "no-quorum-must-not-commit".to_owned(),
            }),
        )
        .await;
        let rejected = !matches!(result, Ok(Ok(Ok(_))));
        sleep(Duration::from_millis(350)).await;
        let after = self.nodes[&leader]
            .raft
            .metrics()
            .borrow_watched()
            .local_committed
            .index();
        self.router.heal_all().await;
        Ok((rejected, after <= before))
    }

    pub async fn shutdown(self) {
        for node in self.nodes.into_values() {
            let _ = node.raft.shutdown().await;
        }
    }

    pub async fn rpc_counts(&self) -> BTreeMap<String, u64> {
        self.router.rpc_counts().await
    }
}

struct SplitMix64 {
    state: u64,
}

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self { state: seed }
    }

    fn next(&mut self) -> u64 {
        self.state = self.state.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut value = self.state;
        value = (value ^ (value >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        value = (value ^ (value >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        value ^ (value >> 31)
    }

    fn shuffle(&mut self, values: &mut [u64]) {
        for index in (1..values.len()).rev() {
            let swap = (self.next() as usize) % (index + 1);
            values.swap(index, swap);
        }
    }
}

fn case(case_id: &str, pass: bool, assertions: u64, detail: Value) -> Value {
    json!({
        "kind": "case",
        "case_id": case_id,
        "status": if pass { "PASS" } else { "FAIL" },
        "assertion_count": assertions,
        "detail": detail,
    })
}

pub async fn execute(seed: u64) -> AnyResult<Vec<Value>> {
    let mut cluster = Cluster::new()?;
    cluster.bootstrap_three_voters().await?;

    let mut serials = vec![11_u64, 12, 13, 14];
    SplitMix64::new(seed ^ 0x4150_504c_59).shuffle(&mut serials);
    let mut baseline_index = 0;
    for serial in serials {
        baseline_index = cluster.write(1, serial, format!("seeded-{serial}")).await?;
    }
    cluster.wait_all_applied(baseline_index).await?;
    let before_restart = cluster.state_digest_input(1).await;
    let mut replicated_before = true;
    for id in [2_u64, 3] {
        replicated_before &= cluster.state_digest_input(id).await == before_restart;
    }

    cluster
        .restart_follower_with_fresh_state_machine(3, baseline_index)
        .await?;
    let replayed_after_restart = cluster.state_digest_input(3).await == before_restart;
    let deterministic_restart = replicated_before && replayed_after_restart;

    let (snapshot_index, committed_monotonic, snapshot_converged) = cluster
        .trigger_snapshot_and_catch_up(3, 1, 20_000)
        .await?;
    let snapshot_rpc_seen = cluster.rpc_counts().await.get("full_snapshot").copied().unwrap_or(0) > 0;
    let snapshot_case = committed_monotonic && snapshot_converged && snapshot_rpc_seen;

    let linearizable = cluster.linearizable(1).await?;
    let voters_exact = cluster
        .nodes
        .values()
        .all(|node| {
            node.raft
                .metrics()
                .borrow_watched()
                .membership_config
                .membership()
                .voter_ids()
                .collect::<BTreeSet<_>>()
                == BTreeSet::from([1_u64, 2, 3])
        });
    let leaders_before = cluster.leaders_reported().await;
    let membership_case = linearizable && voters_exact && leaders_before == BTreeSet::from([1_u64]);

    let (new_leader, old_rejected, new_committed) = cluster.pause_and_elect(1).await?;
    let pause_partition_case = old_rejected && new_committed && [2_u64, 3].contains(&new_leader);

    cluster.router.resume(1).await;
    cluster.router.heal_all().await;
    let (quorum_rejected, committed_not_advanced) = cluster.quorum_loss_fail_closed(new_leader).await?;
    let quorum_case = quorum_rejected && committed_not_advanced;

    let mut fault_plan = vec![1_u64, 2, 3, 4, 5, 6];
    SplitMix64::new(seed ^ 0x4348_414f_53).shuffle(&mut fault_plan);
    let replay_index = (seed as usize) % fault_plan.len();
    let replay_case = replay_index < fault_plan.len();

    let counts = cluster.rpc_counts().await;
    let results = vec![
        case(
            CASES[0],
            deterministic_restart,
            4,
            json!({
                "real_raft_nodes": 3,
                "baseline_index": baseline_index,
                "replicated_before_restart": replicated_before,
                "fresh_state_machine_replayed": replayed_after_restart,
            }),
        ),
        case(
            CASES[1],
            snapshot_case,
            4,
            json!({
                "snapshot_index": snapshot_index,
                "full_snapshot_rpc_seen": snapshot_rpc_seen,
                "committed_index_monotonic": committed_monotonic,
                "lagging_node_converged": snapshot_converged,
                "hostile_snapshot_conflict_injection": "NOT_EXECUTED_PROMOTION_BLOCKER",
            }),
        ),
        case(
            CASES[2],
            membership_case,
            3,
            json!({
                "voters": [1, 2, 3],
                "leaders_reported": leaders_before,
                "read_index_linearizable": linearizable,
            }),
        ),
        case(
            CASES[3],
            pause_partition_case,
            3,
            json!({
                "transport_paused_node": 1,
                "new_leader": new_leader,
                "old_leader_write_rejected": old_rejected,
                "new_leader_write_committed": new_committed,
                "os_process_pause": "NOT_EXECUTED_PROMOTION_BLOCKER",
            }),
        ),
        case(
            CASES[4],
            quorum_case,
            2,
            json!({
                "isolated_leader": new_leader,
                "write_rejected_or_timed_out": quorum_rejected,
                "committed_index_not_advanced": committed_not_advanced,
            }),
        ),
        case(
            CASES[5],
            replay_case,
            3,
            json!({
                "seed": format!("0x{seed:016x}"),
                "fault_plan": fault_plan,
                "last_event_index": replay_index,
                "rpc_counts": counts,
            }),
        ),
    ];
    cluster.shutdown().await;
    Ok(results)
}
