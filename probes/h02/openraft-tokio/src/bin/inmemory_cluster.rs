mod inmemory_cluster {
    pub mod cluster;
    pub mod network;
}

use serde_json::json;

const CANDIDATE_ID: &str = "HB-DEP-RAFT-OPENRAFT";
const VERSION: &str = "0.10.0-alpha.33";
const PROFILE_ID: &str = "HB-H02-BEHAVIOR-RAFT-OPENRAFT-INMEMORY-0_10_0_ALPHA_33";

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

#[tokio::main(flavor = "multi_thread", worker_threads = 4)]
async fn main() {
    let seed = parse_seed();
    println!(
        "{}",
        json!({
            "kind": "meta",
            "candidate_id": CANDIDATE_ID,
            "version": VERSION,
            "profile_id": PROFILE_ID,
            "domain": "RAFT",
            "seed": format!("0x{seed:016x}"),
            "execution_scope": "REAL_OPENRAFT_INMEMORY_CLUSTER_WITH_TEST_MEMSTORE",
            "durability_class": "TEST_ONLY_IN_MEMORY_NO_PRODUCTION_CLAIM",
            "qualification": false,
            "selection_effect": "NONE",
            "authority_effect": "NONE",
        })
    );

    match inmemory_cluster::cluster::execute(seed).await {
        Ok(cases) => {
            for case in cases {
                println!("{case}");
            }
        }
        Err(error) => {
            println!(
                "{}",
                json!({
                    "kind": "harness_error",
                    "status": "BLOCKED",
                    "error_class": "OPENRAFT_INMEMORY_CLUSTER_EXECUTION_FAILED",
                    "message": error.to_string(),
                    "qualification": false,
                    "selection_effect": "NONE",
                    "authority_effect": "NONE",
                })
            );
            std::process::exit(1);
        }
    }
}
