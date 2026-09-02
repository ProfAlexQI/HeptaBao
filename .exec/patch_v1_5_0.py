#!/usr/bin/env python3
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
patched = 0


def replace(old: str, new: str, count: int = 1) -> None:
    global text, patched
    actual = text.count(old)
    if actual != count:
        raise SystemExit(f"patch target count mismatch: expected {count}, found {actual}: {old[:120]!r}")
    text = text.replace(old, new, count)
    patched += 1


replace(
    '''        let selected = Self::validate_versions(versions, requested)?;\n        for entry in versions { if selected.contains(&entry.version) { if entry.destroyed { return Err(KvError::Destroyed); } entry.deleted = true; } }\n        Ok(())''',
    '''        let selected = Self::validate_versions(versions, requested)?;\n        if versions.iter().any(|entry| selected.contains(&entry.version) && entry.destroyed) { return Err(KvError::Destroyed); }\n        for entry in versions { if selected.contains(&entry.version) { entry.deleted = true; } }\n        Ok(())''',
)
replace(
    '''        Operation::Delete { path, versions } | Operation::Undelete { path, versions } | Operation::Destroy { path, versions } => { feed(&mut hash, path.as_bytes()); for version in versions { feed(&mut hash, &version.to_be_bytes()); } }''',
    '''        Operation::Delete { path, versions } => { feed(&mut hash, b"delete"); feed(&mut hash, path.as_bytes()); for version in versions { feed(&mut hash, &version.to_be_bytes()); } }\n        Operation::Undelete { path, versions } => { feed(&mut hash, b"undelete"); feed(&mut hash, path.as_bytes()); for version in versions { feed(&mut hash, &version.to_be_bytes()); } }\n        Operation::Destroy { path, versions } => { feed(&mut hash, b"destroy"); feed(&mut hash, path.as_bytes()); for version in versions { feed(&mut hash, &version.to_be_bytes()); } }''',
)
replace(
    '''    feed(&mut hash, request.id.as_str().as_bytes()); feed(&mut hash, request.namespace.as_str().as_bytes()); feed(&mut hash, request.token.as_str().as_bytes()); feed(&mut hash, &request.now_ms.to_be_bytes());''',
    '''    feed(&mut hash, request.id.as_str().as_bytes()); feed(&mut hash, request.namespace.as_str().as_bytes()); feed(&mut hash, request.token.as_str().as_bytes());''',
)
replace(
    '''enum LedgerState { InProgress(RequestDigest), OutcomeUnknown(RequestDigest, Response), Completed(RequestDigest, Response) }''',
    '''enum LedgerState { InProgress(RequestDigest), FailedOutcomeUnknown(RequestDigest), OutcomeUnknown(RequestDigest, Response), Completed(RequestDigest, Response) }''',
)
replace(
    '''                LedgerState::OutcomeUnknown(existing, _) if existing == digest => Err(ControlPlaneError::OutcomeUnknown),\n                LedgerState::InProgress(existing) if existing == digest => Err(ControlPlaneError::RequestInProgress),\n                LedgerState::Completed(_, _) | LedgerState::OutcomeUnknown(_, _) | LedgerState::InProgress(_) => Err(ControlPlaneError::RequestIdConflict),''',
    '''                LedgerState::OutcomeUnknown(existing, _) if existing == digest => Err(ControlPlaneError::OutcomeUnknown),\n                LedgerState::FailedOutcomeUnknown(existing) if existing == digest => Err(ControlPlaneError::OutcomeUnknown),\n                LedgerState::InProgress(existing) if existing == digest => Err(ControlPlaneError::RequestInProgress),\n                LedgerState::Completed(_, _) | LedgerState::OutcomeUnknown(_, _) | LedgerState::FailedOutcomeUnknown(_) | LedgerState::InProgress(_) => Err(ControlPlaneError::RequestIdConflict),''',
)
replace(
    '''                if self.audit.record_outcome(outcome).is_err() { self.ledger.insert(request.id, LedgerState::InProgress(digest)); return Err(ControlPlaneError::AuditOutcomeUnknown); }''',
    '''                if self.audit.record_outcome(outcome).is_err() { self.ledger.insert(request.id, LedgerState::FailedOutcomeUnknown(digest)); return Err(ControlPlaneError::AuditOutcomeUnknown); }''',
)
replace(
    '''    RootImmutable,\n}''',
    '''    RootImmutable,\n    HasActiveChildren,\n}''',
)
replace(
    '''        if id == &NamespaceId::root() { return Err(NamespaceError::RootImmutable); }\n        let record = self.by_id.get_mut(id).ok_or(NamespaceError::NotFound)?;\n        record.active = false;\n        Ok(())''',
    '''        if id == &NamespaceId::root() { return Err(NamespaceError::RootImmutable); }\n        if self.by_id.values().any(|record| record.active && record.parent.as_ref() == Some(id)) { return Err(NamespaceError::HasActiveChildren); }\n        let record = self.by_id.get_mut(id).ok_or(NamespaceError::NotFound)?;\n        record.active = false;\n        Ok(())''',
)
replace(
    '''| current gate | `.github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml` |\n\n## Supersession chain''',
    '''| current gate | `.github/workflows/plan-v1.5.0-control-plane-vertical-slice.yml` |\n\n## Inherited normative set\n\n| Subject | Inherited document |\n|---|---|\n| V1.4.7 plan | `docs/plan/HEPTABAO_PLAN_V1_4_7_POST_MERGE_TRUTH_AND_EXTERNAL_ADMISSION.md` |\n| V1.4.7 status | `planning/HEPTABAO_V1_4_7_POST_MERGE_TRUTH_STATUS.yaml` |\n| V1.4.7 blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_7.yaml` |\n| V1.4.7 external admission | `docs/governance/HEPTABAO_EXTERNAL_COMPLETION_ADMISSION_PROTOCOL_V1.md` |\n| V1.4.6 authoritative recovery closure | `docs/plan/HEPTABAO_PLAN_V1_4_6_AUTHORITATIVE_RECOVERY_CLOSURE.md` |\n| V1.4.6 status | `planning/HEPTABAO_V1_4_6_AUTHORITATIVE_RECOVERY_STATUS.yaml` |\n| V1.4.6 blocker register | `planning/HEPTABAO_BLOCKER_REGISTER_V1_4_6.yaml` |\n| authoritative recovery protocol | `docs/recovery/HEPTABAO_AUTHORITATIVE_RECOVERY_PROTOCOL_V1.md` |\n| V1.4.5 security invariant closure | `docs/security/HEPTABAO_SECURITY_INVARIANT_CLOSURE_V1.md` |\n| V1.4.4 historical coverage | `planning/HEPTABAO_MODULE_DOCUMENTATION_COVERAGE_V1_4_4.yaml` |\n\n## Supersession chain''',
)

path.write_text(text, encoding="utf-8")
print(f"patched {patched} V1.5.0 materializer targets")
