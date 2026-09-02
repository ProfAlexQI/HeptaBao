#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};

#[derive(Clone, Copy, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct NodeId(u64);

impl NodeId {
    pub fn new(value: u64) -> Result<Self, HaError> {
        if value == 0 {
            Err(HaError::InvalidNode)
        } else {
            Ok(Self(value))
        }
    }

    pub fn get(self) -> u64 {
        self.0
    }
}

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct CommandId(String);

impl CommandId {
    pub fn parse(value: &str) -> Result<Self, HaError> {
        if value.is_empty()
            || value.len() > 128
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err(HaError::InvalidCommandId);
        }
        Ok(Self(value.to_owned()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct LeaderFence {
    pub node: NodeId,
    pub term: u64,
    pub epoch: u64,
}

impl LeaderFence {
    pub fn new(node: NodeId, term: u64, epoch: u64) -> Result<Self, HaError> {
        if term == 0 || epoch == 0 {
            return Err(HaError::InvalidFence);
        }
        Ok(Self { node, term, epoch })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ReplicatedCommand {
    pub id: CommandId,
    pub term: u64,
    pub index: u64,
    pub payload_digest: [u8; 32],
}

impl ReplicatedCommand {
    pub fn new(
        id: CommandId,
        term: u64,
        index: u64,
        payload_digest: [u8; 32],
    ) -> Result<Self, HaError> {
        if term == 0 || index == 0 || payload_digest == [0; 32] {
            return Err(HaError::InvalidCommand);
        }
        Ok(Self {
            id,
            term,
            index,
            payload_digest,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Snapshot {
    pub term: u64,
    pub applied_index: u64,
    pub membership: BTreeSet<NodeId>,
    pub state_digest: [u8; 32],
}

impl Snapshot {
    pub fn new(
        term: u64,
        applied_index: u64,
        membership: BTreeSet<NodeId>,
        state_digest: [u8; 32],
    ) -> Result<Self, HaError> {
        if term == 0
            || applied_index == 0
            || membership.is_empty()
            || state_digest == [0; 32]
        {
            return Err(HaError::InvalidSnapshot);
        }
        Ok(Self {
            term,
            applied_index,
            membership,
            state_digest,
        })
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ApplyDisposition {
    Applied,
    Duplicate,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum HaError {
    InvalidNode,
    InvalidCommandId,
    InvalidCommand,
    InvalidFence,
    InvalidMembership,
    InvalidSnapshot,
    StaleFence,
    TermRegression,
    IndexGap,
    CommitRegression,
    ApplyBeyondCommit,
    CommandConflict,
    SnapshotRegression,
    SnapshotConflict,
}

#[derive(Clone, Debug)]
pub struct HaStateMachine {
    term: u64,
    commit_index: u64,
    applied_index: u64,
    leader_fence: Option<LeaderFence>,
    membership: BTreeSet<NodeId>,
    applied: BTreeMap<CommandId, [u8; 32]>,
    snapshot_digest: Option<[u8; 32]>,
}

impl HaStateMachine {
    pub fn new(initial_node: NodeId) -> Self {
        Self {
            term: 0,
            commit_index: 0,
            applied_index: 0,
            leader_fence: None,
            membership: BTreeSet::from([initial_node]),
            applied: BTreeMap::new(),
            snapshot_digest: None,
        }
    }

    pub fn term(&self) -> u64 {
        self.term
    }

    pub fn commit_index(&self) -> u64 {
        self.commit_index
    }

    pub fn applied_index(&self) -> u64 {
        self.applied_index
    }

    pub fn membership(&self) -> &BTreeSet<NodeId> {
        &self.membership
    }

    pub fn install_leader_fence(&mut self, fence: LeaderFence) -> Result<(), HaError> {
        if fence.term < self.term {
            return Err(HaError::TermRegression);
        }
        if let Some(current) = self.leader_fence {
            if fence.term < current.term
                || (fence.term == current.term && fence.epoch <= current.epoch)
            {
                return Err(HaError::StaleFence);
            }
        }
        self.term = fence.term;
        self.leader_fence = Some(fence);
        Ok(())
    }

    pub fn commit(&mut self, fence: LeaderFence, index: u64) -> Result<(), HaError> {
        self.require_fence(fence)?;
        let expected = self
            .commit_index
            .checked_add(1)
            .ok_or(HaError::IndexGap)?;
        if index != expected {
            return Err(if index < expected {
                HaError::CommitRegression
            } else {
                HaError::IndexGap
            });
        }
        self.commit_index = index;
        Ok(())
    }

    pub fn apply(
        &mut self,
        fence: LeaderFence,
        command: ReplicatedCommand,
    ) -> Result<ApplyDisposition, HaError> {
        self.require_fence(fence)?;
        if command.term != self.term {
            return Err(HaError::TermRegression);
        }
        if let Some(existing) = self.applied.get(&command.id) {
            return if existing == &command.payload_digest {
                Ok(ApplyDisposition::Duplicate)
            } else {
                Err(HaError::CommandConflict)
            };
        }
        let expected = self
            .applied_index
            .checked_add(1)
            .ok_or(HaError::IndexGap)?;
        if command.index != expected {
            return Err(HaError::IndexGap);
        }
        if command.index > self.commit_index {
            return Err(HaError::ApplyBeyondCommit);
        }
        self.applied.insert(command.id, command.payload_digest);
        self.applied_index = command.index;
        Ok(ApplyDisposition::Applied)
    }

    pub fn change_membership(
        &mut self,
        fence: LeaderFence,
        next: BTreeSet<NodeId>,
    ) -> Result<(), HaError> {
        self.require_fence(fence)?;
        if next.is_empty() {
            return Err(HaError::InvalidMembership);
        }
        self.membership = next;
        Ok(())
    }

    pub fn install_snapshot(&mut self, snapshot: Snapshot) -> Result<(), HaError> {
        if snapshot.term < self.term || snapshot.applied_index < self.applied_index {
            return Err(HaError::SnapshotRegression);
        }
        if snapshot.applied_index > self.commit_index && self.commit_index != 0 {
            return Err(HaError::ApplyBeyondCommit);
        }
        if snapshot.applied_index == self.applied_index {
            if self.snapshot_digest.is_some_and(|digest| digest != snapshot.state_digest) {
                return Err(HaError::SnapshotConflict);
            }
        }
        self.term = snapshot.term;
        self.commit_index = self.commit_index.max(snapshot.applied_index);
        self.applied_index = snapshot.applied_index;
        self.membership = snapshot.membership;
        self.snapshot_digest = Some(snapshot.state_digest);
        self.applied.clear();
        self.leader_fence = None;
        Ok(())
    }

    fn require_fence(&self, supplied: LeaderFence) -> Result<(), HaError> {
        match self.leader_fence {
            Some(current) if current == supplied => Ok(()),
            _ => Err(HaError::StaleFence),
        }
    }
}

impl Default for HaStateMachine {
    fn default() -> Self {
        Self::new(NodeId(1))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn digest(byte: u8) -> [u8; 32] {
        [byte; 32]
    }

    #[test]
    fn stale_leader_and_index_gaps_fail_closed() {
        let Ok(node) = NodeId::new(1) else {
            assert!(false);
            return;
        };
        let Ok(fence) = LeaderFence::new(node, 1, 1) else {
            assert!(false);
            return;
        };
        let mut state = HaStateMachine::new(node);
        assert_eq!(state.install_leader_fence(fence), Ok(()));
        assert_eq!(state.commit(fence, 2), Err(HaError::IndexGap));
        assert_eq!(state.commit(fence, 1), Ok(()));
        let Ok(stale) = LeaderFence::new(node, 1, 1) else {
            assert!(false);
            return;
        };
        assert_eq!(state.install_leader_fence(stale), Err(HaError::StaleFence));
    }

    #[test]
    fn duplicate_commands_are_idempotent_but_conflicts_are_rejected() {
        let Ok(node) = NodeId::new(1) else {
            assert!(false);
            return;
        };
        let Ok(fence) = LeaderFence::new(node, 2, 1) else {
            assert!(false);
            return;
        };
        let Ok(id) = CommandId::parse("command-0001") else {
            assert!(false);
            return;
        };
        let Ok(command) = ReplicatedCommand::new(id.clone(), 2, 1, digest(1)) else {
            assert!(false);
            return;
        };
        let mut state = HaStateMachine::new(node);
        assert_eq!(state.install_leader_fence(fence), Ok(()));
        assert_eq!(state.commit(fence, 1), Ok(()));
        assert_eq!(state.apply(fence, command.clone()), Ok(ApplyDisposition::Applied));
        assert_eq!(state.apply(fence, command), Ok(ApplyDisposition::Duplicate));
        let Ok(conflict) = ReplicatedCommand::new(id, 2, 1, digest(2)) else {
            assert!(false);
            return;
        };
        assert_eq!(state.apply(fence, conflict), Err(HaError::CommandConflict));
    }

    #[test]
    fn snapshots_cannot_regress_or silently_change_equal_index_state() {
        let Ok(node) = NodeId::new(1) else {
            assert!(false);
            return;
        };
        let Ok(first) = Snapshot::new(2, 4, BTreeSet::from([node]), digest(3)) else {
            assert!(false);
            return;
        };
        let mut state = HaStateMachine::new(node);
        assert_eq!(state.install_snapshot(first), Ok(()));
        let Ok(regression) = Snapshot::new(2, 3, BTreeSet::from([node]), digest(3)) else {
            assert!(false);
            return;
        };
        assert_eq!(
            state.install_snapshot(regression),
            Err(HaError::SnapshotRegression)
        );
        let Ok(conflict) = Snapshot::new(2, 4, BTreeSet::from([node]), digest(4)) else {
            assert!(false);
            return;
        };
        assert_eq!(
            state.install_snapshot(conflict),
            Err(HaError::SnapshotConflict)
        );
    }
}
