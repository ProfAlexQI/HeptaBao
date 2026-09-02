#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};

use heptabao_kms_contracts::{sha256, Digest32};

#[derive(Clone, Debug, Eq, Hash, Ord, PartialEq, PartialOrd)]
pub struct CaseId(String);

impl CaseId {
    pub fn parse(value: &str) -> Result<Self, CompatibilityError> {
        if value.is_empty()
            || value.len() > 128
            || !value
                .bytes()
                .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'-' | b'_' | b'.'))
        {
            return Err(CompatibilityError::InvalidCaseId);
        }
        Ok(Self(value.to_owned()))
    }

    pub fn as_str(&self) -> &str {
        &self.0
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompatibilityProfile {
    baseline_version: String,
    case_ids: BTreeSet<CaseId>,
    intentional_divergences: BTreeMap<CaseId, String>,
    ignored_headers: BTreeSet<String>,
}

impl CompatibilityProfile {
    pub fn new(
        baseline_version: &str,
        case_ids: BTreeSet<CaseId>,
        intentional_divergences: BTreeMap<CaseId, String>,
        ignored_headers: BTreeSet<String>,
    ) -> Result<Self, CompatibilityError> {
        if baseline_version.is_empty() || case_ids.is_empty() {
            return Err(CompatibilityError::InvalidProfile);
        }
        if intentional_divergences
            .iter()
            .any(|(case, reason)| !case_ids.contains(case) || reason.trim().is_empty())
        {
            return Err(CompatibilityError::InvalidDivergence);
        }
        if ignored_headers.iter().any(|name| !valid_header_name(name)) {
            return Err(CompatibilityError::InvalidHeader);
        }
        Ok(Self {
            baseline_version: baseline_version.to_owned(),
            case_ids,
            intentional_divergences,
            ignored_headers,
        })
    }

    pub fn baseline_version(&self) -> &str {
        &self.baseline_version
    }

    pub fn case_ids(&self) -> &BTreeSet<CaseId> {
        &self.case_ids
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ObservedExchange {
    pub status: u16,
    pub headers: BTreeMap<String, String>,
    pub body_digest: Digest32,
    pub side_effect_digest: Digest32,
}

impl ObservedExchange {
    pub fn capture(
        status: u16,
        headers: &BTreeMap<String, String>,
        body: &[u8],
        side_effects: &[u8],
    ) -> Result<Self, CompatibilityError> {
        if !(100..=599).contains(&status) {
            return Err(CompatibilityError::InvalidStatus);
        }
        let mut normalized = BTreeMap::new();
        for (name, value) in headers {
            if !valid_header_name(name) || value.contains(['\r', '\n']) {
                return Err(CompatibilityError::InvalidHeader);
            }
            let canonical = name.to_ascii_lowercase();
            if normalized.insert(canonical, value.clone()).is_some() {
                return Err(CompatibilityError::DuplicateHeader);
            }
        }
        Ok(Self {
            status,
            headers: normalized,
            body_digest: sha256(body),
            side_effect_digest: sha256(side_effects),
        })
    }

    fn equivalent_to(
        &self,
        other: &Self,
        ignored_headers: &BTreeSet<String>,
    ) -> bool {
        self.status == other.status
            && filtered_headers(&self.headers, ignored_headers)
                == filtered_headers(&other.headers, ignored_headers)
            && self.body_digest == other.body_digest
            && self.side_effect_digest == other.side_effect_digest
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CaseObservation {
    pub oracle: ObservedExchange,
    pub candidate: ObservedExchange,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CaseDisposition {
    Equivalent,
    IntentionalDivergence(String),
    Mismatch,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CaseResult {
    pub id: CaseId,
    pub disposition: CaseDisposition,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct CompatibilityReport {
    pub baseline_version: String,
    pub equivalent_cases: usize,
    pub denominator: usize,
    pub intentional_divergences: usize,
    pub mismatches: usize,
    pub results: Vec<CaseResult>,
    pub evidence_digest: Digest32,
    pub compatibility_claim: bool,
    pub authority_effect: &'static str,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum CompatibilityError {
    InvalidCaseId,
    InvalidProfile,
    InvalidDivergence,
    InvalidHeader,
    DuplicateHeader,
    InvalidStatus,
    CaseSetMismatch,
}

pub fn evaluate(
    profile: &CompatibilityProfile,
    observations: &BTreeMap<CaseId, CaseObservation>,
) -> Result<CompatibilityReport, CompatibilityError> {
    let observed_ids: BTreeSet<_> = observations.keys().cloned().collect();
    if observed_ids != profile.case_ids {
        return Err(CompatibilityError::CaseSetMismatch);
    }

    let mut equivalent_cases = 0_usize;
    let mut divergence_count = 0_usize;
    let mut mismatch_count = 0_usize;
    let mut results = Vec::with_capacity(profile.case_ids.len());
    let mut preimage = Vec::new();
    feed(&mut preimage, profile.baseline_version.as_bytes());

    for id in &profile.case_ids {
        let observation = observations
            .get(id)
            .ok_or(CompatibilityError::CaseSetMismatch)?;
        let equivalent = observation
            .oracle
            .equivalent_to(&observation.candidate, &profile.ignored_headers);
        let disposition = if equivalent {
            equivalent_cases = equivalent_cases.saturating_add(1);
            CaseDisposition::Equivalent
        } else if let Some(reason) = profile.intentional_divergences.get(id) {
            divergence_count = divergence_count.saturating_add(1);
            CaseDisposition::IntentionalDivergence(reason.clone())
        } else {
            mismatch_count = mismatch_count.saturating_add(1);
            CaseDisposition::Mismatch
        };
        feed(&mut preimage, id.as_str().as_bytes());
        feed(&mut preimage, &[disposition_tag(&disposition)]);
        feed(&mut preimage, observation.oracle.body_digest.as_bytes());
        feed(
            &mut preimage,
            observation.oracle.side_effect_digest.as_bytes(),
        );
        feed(&mut preimage, observation.candidate.body_digest.as_bytes());
        feed(
            &mut preimage,
            observation.candidate.side_effect_digest.as_bytes(),
        );
        results.push(CaseResult {
            id: id.clone(),
            disposition,
        });
    }

    Ok(CompatibilityReport {
        baseline_version: profile.baseline_version.clone(),
        equivalent_cases,
        denominator: profile.case_ids.len(),
        intentional_divergences: divergence_count,
        mismatches: mismatch_count,
        results,
        evidence_digest: sha256(&preimage),
        compatibility_claim: false,
        authority_effect: "NONE",
    })
}

fn filtered_headers(
    headers: &BTreeMap<String, String>,
    ignored: &BTreeSet<String>,
) -> BTreeMap<String, String> {
    headers
        .iter()
        .filter(|(name, _)| !ignored.contains(*name))
        .map(|(name, value)| (name.clone(), value.clone()))
        .collect()
}

fn valid_header_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

fn feed(output: &mut Vec<u8>, value: &[u8]) {
    output.extend_from_slice(&(value.len() as u64).to_be_bytes());
    output.extend_from_slice(value);
}

fn disposition_tag(value: &CaseDisposition) -> u8 {
    match value {
        CaseDisposition::Equivalent => 1,
        CaseDisposition::IntentionalDivergence(_) => 2,
        CaseDisposition::Mismatch => 3,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn case(value: &str) -> Option<CaseId> {
        CaseId::parse(value).ok()
    }

    fn exchange(body: &[u8], effects: &[u8]) -> Option<ObservedExchange> {
        ObservedExchange::capture(200, &BTreeMap::new(), body, effects).ok()
    }

    #[test]
    fn denominator_cannot_be_shrunk_or_extended() {
        let (Some(first), Some(second)) = (case("case-a"), case("case-b")) else {
            assert!(false);
            return;
        };
        let Ok(profile) = CompatibilityProfile::new(
            "openbao-test-baseline",
            BTreeSet::from([first.clone(), second]),
            BTreeMap::new(),
            BTreeSet::new(),
        ) else {
            assert!(false);
            return;
        };
        let Some(value) = exchange(b"ok", b"audit=1") else {
            assert!(false);
            return;
        };
        let observations = BTreeMap::from([(
            first,
            CaseObservation {
                oracle: value.clone(),
                candidate: value,
            },
        )]);
        assert_eq!(
            evaluate(&profile, &observations),
            Err(CompatibilityError::CaseSetMismatch)
        );
    }

    #[test]
    fn side_effect_mismatch_is_not_hidden_by_equal_response_bytes() {
        let Some(id) = case("case-effects") else {
            assert!(false);
            return;
        };
        let Ok(profile) = CompatibilityProfile::new(
            "openbao-test-baseline",
            BTreeSet::from([id.clone()]),
            BTreeMap::new(),
            BTreeSet::new(),
        ) else {
            assert!(false);
            return;
        };
        let (Some(oracle), Some(candidate)) = (
            exchange(b"ok", b"audit=1"),
            exchange(b"ok", b"audit=0"),
        ) else {
            assert!(false);
            return;
        };
        let observations = BTreeMap::from([(id, CaseObservation { oracle, candidate })]);
        let Ok(report) = evaluate(&profile, &observations) else {
            assert!(false);
            return;
        };
        assert_eq!(report.mismatches, 1);
        assert!(!report.compatibility_claim);
        assert_eq!(report.authority_effect, "NONE");
    }

    #[test]
    fn intentional_divergence_is_explicit_and_never_becomes_authority() {
        let Some(id) = case("case-divergence") else {
            assert!(false);
            return;
        };
        let Ok(profile) = CompatibilityProfile::new(
            "openbao-test-baseline",
            BTreeSet::from([id.clone()]),
            BTreeMap::from([(id.clone(), "documented status difference".to_owned())]),
            BTreeSet::new(),
        ) else {
            assert!(false);
            return;
        };
        let (Some(oracle), Some(candidate)) = (exchange(b"one", b"a"), exchange(b"two", b"b")) else {
            assert!(false);
            return;
        };
        let observations = BTreeMap::from([(id, CaseObservation { oracle, candidate })]);
        let Ok(report) = evaluate(&profile, &observations) else {
            assert!(false);
            return;
        };
        assert_eq!(report.intentional_divergences, 1);
        assert_eq!(report.mismatches, 0);
        assert!(!report.compatibility_claim);
    }
}
