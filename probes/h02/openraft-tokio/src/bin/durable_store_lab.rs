mod durable_store_lab {
    pub mod cluster;
    pub mod network;
    pub mod store;
}

use std::collections::BTreeMap;
use std::fs;
use std::path::{Path, PathBuf};

use durable_store_lab::cluster::DurableCluster;
use durable_store_lab::store::{DurableLogStore, DurableStateMachine, flip_first_payload_byte};
use serde_json::{Value, json};
use tokio::task::spawn_blocking;

const CANDIDATE_ID: &str = "HB-DEP-RAFT-OPENRAFT";
const VERSION: &str = "0.10.0-alpha.33";
const PROFILE_ID: &str = "HB-H02-OPENRAFT-DURABLE-STORE-V1";

fn parse_seed() -> u64 {
    let args = std::env::args().collect::<Vec<_>>();
    let raw = args
        .windows(2)
        .find(|pair| pair[0] == "--seed")
        .map(|pair| pair[1].as_str())
        .unwrap_or("0x5eed20260828cafe");
    let trimmed = raw.strip_prefix("0x").unwrap_or(raw);
    u64::from_str_radix(trimmed, 16).unwrap_or_else(|_| panic!("invalid seed: {raw}"))
}

fn copy_tree(source: &Path, destination: &Path) -> std::io::Result<()> {
    if destination.exists() {
        fs::remove_dir_all(destination)?;
    }
    fs::create_dir_all(destination)?;
    for entry in fs::read_dir(source)? {
        let entry = entry?;
        let source_path = entry.path();
        let destination_path = destination.join(entry.file_name());
        if entry.file_type()?.is_dir() {
            copy_tree(&source_path, &destination_path)?;
        } else {
            fs::copy(source_path, destination_path)?;
        }
    }
    Ok(())
}

fn case(case_id: &str, pass: bool, detail: Value) -> Value {
    json!({
        "case_id": case_id,
        "status": if pass { "PASS" } else { "FAIL" },
        "detail": detail,
    })
}

async fn execute(seed: u64) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
    let root = std::env::temp_dir().join(format!(
        "heptabao-h02-durable-openraft-{}-{seed:016x}",
        std::process::id()
    ));
    let _ = fs::remove_dir_all(&root);
    fs::create_dir_all(&root)?;

    let result = async {
        let mut serials = vec![seed ^ 11, seed.rotate_left(7) ^ 12, seed.rotate_left(19) ^ 13];
        serials.sort_unstable();

        let mut first = DurableCluster::new(&root)?;
        first.bootstrap_three_voters().await?;
        let mut last_index = 0_u64;
        for (offset, serial) in serials.iter().copied().enumerate() {
            last_index = first
                .write(1, serial, format!("durable-seeded-{offset}-{serial}"))
                .await?;
        }
        first.wait_all_applied(last_index).await?;
        first.read_index(1).await?;
        let replicated_before_restart = first.all_states_equal().await;
        let expected_before_restart = first.state(1).await;
        first.trigger_snapshot(1, last_index).await?;
        let first_rpc_counts = first.rpc_counts().await;
        let first_artifacts = first.artifact_paths();
        let all_log_and_state_artifacts_nonempty = first_artifacts
            .iter()
            .filter(|(name, _)| !name.ends_with("snapshot"))
            .all(|(_, path)| fs::metadata(path).is_ok_and(|metadata| metadata.len() > 0));
        let (partition_rejected, committed_not_advanced) = first.exercise_partition(1).await?;
        first.shutdown().await?;

        let mut reopened = DurableCluster::new(&root)?;
        let reopened_leader = reopened.reopen_three_voters().await?;
        reopened.read_index(reopened_leader).await?;
        let recovered_equal = reopened.all_states_equal().await;
        let recovered_state = reopened.state(reopened_leader).await;
        let recovered_matches = recovered_state.client_status == expected_before_restart.client_status;

        let post_restart_index = reopened
            .write(
                reopened_leader,
                seed ^ 0xd00d_f00d,
                "post-restart-committed".to_owned(),
            )
            .await?;
        reopened.wait_all_applied(post_restart_index).await?;
        reopened.trigger_snapshot(reopened_leader, post_restart_index).await?;
        let expected_after_restart = reopened.state(reopened_leader).await;
        let snapshot_source = root
            .join(format!("node-{reopened_leader}"))
            .join("state-machine");
        reopened.shutdown().await?;

        let mut reopened_again = DurableCluster::new(&root)?;
        let second_leader = reopened_again.reopen_three_voters().await?;
        reopened_again.read_index(second_leader).await?;
        let second_state = reopened_again.state(second_leader).await;
        let second_restart_matches =
            reopened_again.all_states_equal().await
                && second_state.client_status == expected_after_restart.client_status;
        reopened_again.shutdown().await?;

        let snapshot_copy = root.join("snapshot-recovery-copy");
        copy_tree(&snapshot_source, &snapshot_copy)?;
        let state_path = snapshot_copy.join("state-machine.bin");
        fs::remove_file(&state_path)?;
        let expected_snapshot_state = expected_after_restart.client_status.clone();
        let snapshot_recovered = spawn_blocking(move || DurableStateMachine::open(snapshot_copy))
            .await??;
        let snapshot_recovery_matches =
            snapshot_recovered.get_state_machine().await.client_status == expected_snapshot_state;

        let corrupt_log_root = root.join("corrupt-log-copy");
        copy_tree(&root.join("node-1").join("log"), &corrupt_log_root)?;
        flip_first_payload_byte(&corrupt_log_root.join("raft-log.bin"))?;
        let corrupt_log_rejected = spawn_blocking(move || DurableLogStore::open(corrupt_log_root))
            .await?
            .is_err();

        let corrupt_state_root = root.join("corrupt-state-copy");
        copy_tree(&root.join("node-1").join("state-machine"), &corrupt_state_root)?;
        flip_first_payload_byte(&corrupt_state_root.join("state-machine.bin"))?;
        let corrupt_state_rejected =
            spawn_blocking(move || DurableStateMachine::open(corrupt_state_root))
                .await?
                .is_err();

        let cases = vec![
            case(
                "durable-three-node-fsync-and-replication",
                replicated_before_restart && all_log_and_state_artifacts_nonempty,
                json!({
                    "last_index": last_index,
                    "states_equal": replicated_before_restart,
                    "artifacts_nonempty": all_log_and_state_artifacts_nonempty,
                    "rpc_counts": first_rpc_counts,
                }),
            ),
            case(
                "durable-full-cluster-restart-and-read-index",
                recovered_equal && recovered_matches,
                json!({
                    "leader": reopened_leader,
                    "states_equal": recovered_equal,
                    "matches_pre_restart": recovered_matches,
                }),
            ),
            case(
                "durable-post-restart-write-survives-second-restart",
                second_restart_matches,
                json!({
                    "leader": second_leader,
                    "post_restart_index": post_restart_index,
                    "matches": second_restart_matches,
                }),
            ),
            case(
                "durable-snapshot-recovers-missing-state-file",
                snapshot_recovery_matches,
                json!({"matches": snapshot_recovery_matches}),
            ),
            case(
                "durable-log-corruption-fails-closed",
                corrupt_log_rejected,
                json!({"rejected": corrupt_log_rejected}),
            ),
            case(
                "durable-state-corruption-fails-closed",
                corrupt_state_rejected,
                json!({"rejected": corrupt_state_rejected}),
            ),
            case(
                "durable-isolated-writer-does-not-advance-commit",
                partition_rejected && committed_not_advanced,
                json!({
                    "write_rejected_or_timed_out": partition_rejected,
                    "committed_not_advanced": committed_not_advanced,
                }),
            ),
        ];
        let pass = cases
            .iter()
            .all(|entry| entry.get("status").and_then(Value::as_str) == Some("PASS"));
        Ok::<Value, Box<dyn std::error::Error + Send + Sync>>(json!({
            "schema": "heptabao.h02-openraft-durable-store-result.v1",
            "candidate_id": CANDIDATE_ID,
            "version": VERSION,
            "profile_id": PROFILE_ID,
            "seed": format!("0x{seed:016x}"),
            "status": if pass { "EXECUTED_PASS" } else { "EXECUTED_FAIL" },
            "cases": cases,
            "scope": {
                "real_openraft_nodes": 3,
                "raft_log_storage_implemented": true,
                "raft_state_machine_implemented": true,
                "vote_persisted_before_return": true,
                "committed_index_persisted": true,
                "log_io_flushed_after_sync_all": true,
                "state_machine_persisted_before_responder": true,
                "snapshot_atomic_publish_and_parent_sync": true,
                "full_cluster_disk_restart": true,
                "read_index_after_restart": true,
                "corruption_rejected": true,
                "kernel_power_loss": false,
                "production_selected": false
            },
            "promotion_effect": "BLOCK_PENDING_POWER_CUT_LAB_MULTI_PROCESS_TIME_NAMESPACE_AND_INDEPENDENT_REVIEW",
            "qualification": false,
            "selection_effect": "NONE",
            "authority_effect": "NONE"
        }))
    }
    .await;

    let _ = fs::remove_dir_all(&root);
    result
}

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    let seed = parse_seed();
    let output = match execute(seed).await {
        Ok(output) => output,
        Err(error) => json!({
            "schema": "heptabao.h02-openraft-durable-store-result.v1",
            "candidate_id": CANDIDATE_ID,
            "version": VERSION,
            "profile_id": PROFILE_ID,
            "seed": format!("0x{seed:016x}"),
            "status": "BLOCKED",
            "reason": error.to_string(),
            "cases": [],
            "qualification": false,
            "selection_effect": "NONE",
            "authority_effect": "NONE"
        }),
    };
    println!("{output}");
    if output.get("status").and_then(Value::as_str) != Some("EXECUTED_PASS") {
        std::process::exit(2);
    }
}

#[allow(dead_code)]
fn _type_anchor(_: BTreeMap<String, PathBuf>) {}
