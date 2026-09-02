#![forbid(unsafe_code)]

use std::collections::BTreeMap;
use std::fmt;

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub enum HttpMethod {
    Get,
    Put,
    Post,
    Delete,
}

impl HttpMethod {
    fn parse(value: &str) -> Result<Self, HttpError> {
        match value {
            "GET" => Ok(Self::Get),
            "PUT" => Ok(Self::Put),
            "POST" => Ok(Self::Post),
            "DELETE" => Ok(Self::Delete),
            _ => Err(HttpError::UnsupportedMethod),
        }
    }
}

#[derive(Clone, Eq, PartialEq)]
pub struct SensitiveBody(Vec<u8>);

impl SensitiveBody {
    pub fn new(value: Vec<u8>) -> Self {
        Self(value)
    }

    pub fn expose(&self) -> &[u8] {
        &self.0
    }

    pub fn len(&self) -> usize {
        self.0.len()
    }

    pub fn is_empty(&self) -> bool {
        self.0.is_empty()
    }

    pub fn into_bytes(mut self) -> Vec<u8> {
        std::mem::take(&mut self.0)
    }
}

impl fmt::Debug for SensitiveBody {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("SensitiveBody")
            .field("len", &self.0.len())
            .finish_non_exhaustive()
    }
}

impl Drop for SensitiveBody {
    fn drop(&mut self) {
        self.0.fill(0);
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HttpRequest {
    pub method: HttpMethod,
    pub target: String,
    pub headers: BTreeMap<String, String>,
    pub body: SensitiveBody,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct HttpResponse {
    pub status: u16,
    pub headers: BTreeMap<String, String>,
    pub body: Vec<u8>,
}

impl HttpResponse {
    pub fn empty(status: u16) -> Self {
        Self {
            status,
            headers: BTreeMap::new(),
            body: Vec::new(),
        }
    }
}

pub trait HttpHandler {
    fn handle(&mut self, request: HttpRequest) -> HttpResponse;
}

#[derive(Clone, Copy, Debug, Eq, PartialEq)]
pub struct HttpLimits {
    pub maximum_head_bytes: usize,
    pub maximum_header_count: usize,
    pub maximum_target_bytes: usize,
    pub maximum_body_bytes: usize,
}

impl HttpLimits {
    pub fn validate(self) -> Result<Self, HttpError> {
        if self.maximum_head_bytes == 0
            || self.maximum_header_count == 0
            || self.maximum_target_bytes == 0
            || self.maximum_body_bytes == 0
        {
            return Err(HttpError::InvalidLimits);
        }
        Ok(self)
    }
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub enum HttpError {
    InvalidLimits,
    HeadTooLarge,
    HeadTerminatorMissing,
    InvalidUtf8,
    InvalidRequestLine,
    UnsupportedMethod,
    UnsupportedVersion,
    InvalidTarget,
    TargetTooLarge,
    TooManyHeaders,
    InvalidHeaderName,
    InvalidHeaderValue,
    DuplicateHeader,
    HostMissing,
    TransferEncodingForbidden,
    InvalidContentLength,
    BodyTooLarge,
    BodyLengthMismatch,
}

pub fn parse_request(input: &[u8], limits: HttpLimits) -> Result<HttpRequest, HttpError> {
    let limits = limits.validate()?;
    let separator = input
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or(HttpError::HeadTerminatorMissing)?;
    let head_length = separator.checked_add(4).ok_or(HttpError::HeadTooLarge)?;
    if head_length > limits.maximum_head_bytes {
        return Err(HttpError::HeadTooLarge);
    }

    let head = std::str::from_utf8(&input[..separator]).map_err(|_| HttpError::InvalidUtf8)?;
    let mut lines = head.split("\r\n");
    let request_line = lines.next().ok_or(HttpError::InvalidRequestLine)?;
    let mut request_parts = request_line.split(' ');
    let method = request_parts.next().ok_or(HttpError::InvalidRequestLine)?;
    let target = request_parts.next().ok_or(HttpError::InvalidRequestLine)?;
    let version = request_parts.next().ok_or(HttpError::InvalidRequestLine)?;
    if request_parts.next().is_some() || method.is_empty() || target.is_empty() || version.is_empty() {
        return Err(HttpError::InvalidRequestLine);
    }
    let method = HttpMethod::parse(method)?;
    if version != "HTTP/1.1" {
        return Err(HttpError::UnsupportedVersion);
    }
    validate_target(target, limits.maximum_target_bytes)?;

    let mut headers = BTreeMap::new();
    for (index, line) in lines.enumerate() {
        if index >= limits.maximum_header_count {
            return Err(HttpError::TooManyHeaders);
        }
        let (name, value) = line.split_once(':').ok_or(HttpError::InvalidHeaderName)?;
        if !valid_header_name(name) {
            return Err(HttpError::InvalidHeaderName);
        }
        let canonical_name = name.to_ascii_lowercase();
        let canonical_value = value.trim_matches([' ', '\t']);
        if canonical_value.is_empty()
            || canonical_value.bytes().any(|byte| byte < 0x20 && byte != b'\t')
            || canonical_value.bytes().any(|byte| byte == 0x7f)
        {
            return Err(HttpError::InvalidHeaderValue);
        }
        if canonical_name == "transfer-encoding" {
            return Err(HttpError::TransferEncodingForbidden);
        }
        if headers
            .insert(canonical_name, canonical_value.to_owned())
            .is_some()
        {
            return Err(HttpError::DuplicateHeader);
        }
    }
    if !headers.contains_key("host") {
        return Err(HttpError::HostMissing);
    }

    let body = &input[head_length..];
    let declared_length = match headers.get("content-length") {
        Some(value) => value
            .parse::<usize>()
            .map_err(|_| HttpError::InvalidContentLength)?,
        None if body.is_empty() => 0,
        None => return Err(HttpError::BodyLengthMismatch),
    };
    if declared_length > limits.maximum_body_bytes {
        return Err(HttpError::BodyTooLarge);
    }
    if body.len() != declared_length {
        return Err(HttpError::BodyLengthMismatch);
    }

    Ok(HttpRequest {
        method,
        target: target.to_owned(),
        headers,
        body: SensitiveBody::new(body.to_vec()),
    })
}

fn validate_target(value: &str, maximum: usize) -> Result<(), HttpError> {
    if value.len() > maximum {
        return Err(HttpError::TargetTooLarge);
    }
    if !value.starts_with('/')
        || value.contains('#')
        || value.bytes().any(|byte| byte <= 0x20 || byte == 0x7f)
        || value.contains("\\")
    {
        return Err(HttpError::InvalidTarget);
    }
    Ok(())
}

fn valid_header_name(value: &str) -> bool {
    !value.is_empty()
        && value.bytes().all(|byte| {
            byte.is_ascii_alphanumeric()
                || matches!(
                    byte,
                    b'!' | b'#' | b'$' | b'%' | b'&' | b'\'' | b'*' | b'+' | b'-' | b'.'
                        | b'^' | b'_' | b'`' | b'|' | b'~'
                )
        })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn limits() -> HttpLimits {
        HttpLimits {
            maximum_head_bytes: 1_024,
            maximum_header_count: 8,
            maximum_target_bytes: 256,
            maximum_body_bytes: 64,
        }
    }

    #[test]
    fn exact_request_parses_and_sensitive_debug_is_redacted() {
        let input = b"PUT /v1/secret/a HTTP/1.1\r\nHost: localhost\r\nContent-Length: 5\r\nX-Request-Id: request-0001\r\n\r\nvalue";
        let Ok(request) = parse_request(input, limits()) else {
            assert!(false);
            return;
        };
        assert_eq!(request.method, HttpMethod::Put);
        assert_eq!(request.target, "/v1/secret/a");
        assert_eq!(request.body.expose(), b"value");
        assert!(!format!("{:?}", request.body).contains("value"));
    }

    #[test]
    fn duplicate_headers_and_length_smuggling_fail_closed() {
        let duplicate = b"GET /v1/sys/health HTTP/1.1\r\nHost: a\r\nHOST: b\r\n\r\n";
        assert_eq!(parse_request(duplicate, limits()), Err(HttpError::DuplicateHeader));
        let mismatch = b"POST /v1/secret/a HTTP/1.1\r\nHost: a\r\nContent-Length: 4\r\n\r\nvalue";
        assert_eq!(parse_request(mismatch, limits()), Err(HttpError::BodyLengthMismatch));
    }

    #[test]
    fn transfer_encoding_and_request_line_smuggling_fail_closed() {
        let transfer = b"POST /v1/secret/a HTTP/1.1\r\nHost: a\r\nTransfer-Encoding: chunked\r\n\r\n";
        assert_eq!(
            parse_request(transfer, limits()),
            Err(HttpError::TransferEncodingForbidden)
        );
        let spaces = b"GET  /v1/sys/health HTTP/1.1\r\nHost: a\r\n\r\n";
        assert_eq!(parse_request(spaces, limits()), Err(HttpError::InvalidRequestLine));
    }
}
