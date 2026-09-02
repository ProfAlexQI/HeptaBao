#![forbid(unsafe_code)]

use std::collections::{BTreeMap, BTreeSet};
use std::net::SocketAddr;

use heptabao_http_api::{HttpMethod, HttpRequest, HttpResponse, SensitiveBody};

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct ProxyPolicy {
    pub allow_plain_loopback: bool,
    pub require_tls_remote: bool,
    pub allowed_headers: BTreeSet<String>,
}

impl ProxyPolicy {
    pub fn validate(&self) -> Result<(), ClientError> {
        if self.allowed_headers.iter().any(|name| !valid_header_name(name)) {
            return Err(ClientError::InvalidPolicy);
        }
        Ok(())
    }

    pub fn authorize_upstream(
        &self,
        address: SocketAddr,
        tls: bool,
    ) -> Result<(), ClientError> {
        self.validate()?;
        if address.ip().is_loopback() {
            if !tls && !self.allow_plain_loopback {
                return Err(ClientError::TlsRequired);
            }
            return Ok(());
        }
        if self.require_tls_remote && !tls {
            return Err(ClientError::TlsRequired);
        }
        Ok(())
    }

    pub fn filter_headers(
        &self,
        headers: &BTreeMap<String, String>,
    ) -> BTreeMap<String, String> {
        headers
            .iter()
            .filter_map(|(name, value)| {
                let canonical = name.to_ascii_lowercase();
                if is_hop_by_hop(&canonical) || !self.allowed_headers.contains(&canonical) {
                    None
                } else {
                    Some((canonical, value.clone()))
                }
            })
            .collect()
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct RequestBuilder {
    method: HttpMethod,
    target: String,
    headers: BTreeMap<String, String>,
    body: Vec<u8>,
}

impl RequestBuilder {
    pub fn new(method: HttpMethod, target: &str) -> Result<Self, ClientError> {
        if !target.starts_with('/')
            || target.contains(['\r', '\n', '#', '\\'])
            || target.len() > 4_096
        {
            return Err(ClientError::InvalidTarget);
        }
        Ok(Self {
            method,
            target: target.to_owned(),
            headers: BTreeMap::new(),
            body: Vec::new(),
        })
    }

    pub fn header(mut self, name: &str, value: &str) -> Result<Self, ClientError> {
        let canonical = name.to_ascii_lowercase();
        if !valid_header_name(&canonical)
            || value.is_empty()
            || value.contains(['\r', '\n'])
            || is_hop_by_hop(&canonical)
        {
            return Err(ClientError::InvalidHeader);
        }
        if self
            .headers
            .insert(canonical, value.to_owned())
            .is_some()
        {
            return Err(ClientError::DuplicateHeader);
        }
        Ok(self)
    }

    pub fn body(mut self, value: Vec<u8>) -> Self {
        self.body = value;
        self
    }

    pub fn build(self) -> Result<HttpRequest, ClientError> {
        if !self.headers.contains_key("x-request-id") {
            return Err(ClientError::RequestIdMissing);
        }
        Ok(HttpRequest {
            method: self.method,
            target: self.target,
            headers: self.headers,
            body: SensitiveBody::new(self.body),
        })
    }
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum RetryDisposition {
    DoNotRetry,
    SafeAfterBackoff,
    ReconcileBeforeRetry,
}

pub fn classify_retry(response: &HttpResponse) -> RetryDisposition {
    if response
        .headers
        .get("x-heptabao-outcome")
        .is_some_and(|value| value == "unknown")
    {
        return RetryDisposition::ReconcileBeforeRetry;
    }
    match response.status {
        429 | 502 | 503 | 504 => RetryDisposition::SafeAfterBackoff,
        _ => RetryDisposition::DoNotRetry,
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum ClientError {
    InvalidPolicy,
    TlsRequired,
    InvalidTarget,
    InvalidHeader,
    DuplicateHeader,
    RequestIdMissing,
}

fn valid_header_name(value: &str) -> bool {
    !value.is_empty()
        && value.len() <= 64
        && value
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'-')
}

fn is_hop_by_hop(value: &str) -> bool {
    matches!(
        value,
        "connection"
            | "keep-alive"
            | "proxy-authenticate"
            | "proxy-authorization"
            | "te"
            | "trailer"
            | "transfer-encoding"
            | "upgrade"
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn remote_plaintext_is_rejected_and_hop_headers_are_stripped() {
        let policy = ProxyPolicy {
            allow_plain_loopback: true,
            require_tls_remote: true,
            allowed_headers: BTreeSet::from([
                "x-request-id".to_owned(),
                "connection".to_owned(),
            ]),
        };
        let Ok(remote) = "192.0.2.10:8200".parse::<SocketAddr>() else {
            assert!(false);
            return;
        };
        assert_eq!(
            policy.authorize_upstream(remote, false),
            Err(ClientError::TlsRequired)
        );
        let filtered = policy.filter_headers(&BTreeMap::from([
            ("X-Request-Id".to_owned(), "request-1".to_owned()),
            ("Connection".to_owned(), "keep-alive".to_owned()),
            ("Authorization".to_owned(), "secret".to_owned()),
        ]));
        assert_eq!(
            filtered,
            BTreeMap::from([("x-request-id".to_owned(), "request-1".to_owned())])
        );
    }

    #[test]
    fn builder_rejects_duplicate_or_missing_request_identity() {
        let Ok(builder) = RequestBuilder::new(HttpMethod::Get, "/v1/sys/health") else {
            assert!(false);
            return;
        };
        assert_eq!(builder.clone().build(), Err(ClientError::RequestIdMissing));
        let Ok(builder) = builder.header("X-Request-Id", "request-1") else {
            assert!(false);
            return;
        };
        assert_eq!(
            builder.clone().header("x-request-id", "request-2"),
            Err(ClientError::DuplicateHeader)
        );
        assert!(builder.build().is_ok());
    }

    #[test]
    fn outcome_unknown_is_never_classified_as_blind_retry() {
        let response = HttpResponse {
            status: 503,
            headers: BTreeMap::from([(
                "x-heptabao-outcome".to_owned(),
                "unknown".to_owned(),
            )]),
            body: Vec::new(),
        };
        assert_eq!(
            classify_retry(&response),
            RetryDisposition::ReconcileBeforeRetry
        );
    }
}
