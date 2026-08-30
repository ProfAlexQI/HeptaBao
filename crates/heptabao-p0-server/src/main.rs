#![forbid(unsafe_code)]

use std::env;
use std::io::{Read, Write};
use std::net::{IpAddr, SocketAddr, TcpListener, TcpStream};
use std::process::ExitCode;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{Duration, Instant};

use heptabao_p0_server::{DevelopmentCredentials, FileAuditSink, P0Response, P0Server};
use heptabao_protocol::{
    parse_http_request, MonotonicTick, ProtocolError, RequestEnvelope, RequestId,
};

static REQUEST_SEQUENCE: AtomicU64 = AtomicU64::new(1);

fn main() -> ExitCode {
    match run() {
        Ok(()) => ExitCode::SUCCESS,
        Err(error) => {
            eprintln!("heptabao-p0-server: {error}");
            ExitCode::FAILURE
        }
    }
}

fn run() -> Result<(), String> {
    let bind = env::var("HEPTABAO_P0_BIND").unwrap_or_else(|_| "127.0.0.1:18200".to_owned());
    let address = bind
        .parse::<SocketAddr>()
        .map_err(|error| format!("invalid HEPTABAO_P0_BIND: {error}"))?;
    if !is_loopback(address.ip()) {
        return Err("P0 listener must bind to a loopback address".to_owned());
    }
    let token = env::var("HEPTABAO_P0_DEV_TOKEN")
        .map_err(|_| "HEPTABAO_P0_DEV_TOKEN is required".to_owned())?;
    let unseal_key = env::var("HEPTABAO_P0_DEV_UNSEAL_KEY")
        .map_err(|_| "HEPTABAO_P0_DEV_UNSEAL_KEY is required".to_owned())?;
    let audit_path = env::var("HEPTABAO_P0_AUDIT_PATH")
        .map_err(|_| "HEPTABAO_P0_AUDIT_PATH is required".to_owned())?;
    let credentials = DevelopmentCredentials::new(token.into_bytes(), unseal_key.into_bytes())
        .map_err(|error| error.to_string())?;
    let audit = FileAuditSink::create_new(audit_path).map_err(|error| error.to_string())?;
    let mut server = P0Server::new(credentials, audit);
    let listener = TcpListener::bind(address).map_err(|error| format!("bind failed: {error}"))?;
    let local_address = listener
        .local_addr()
        .map_err(|error| format!("read local listener address failed: {error}"))?;
    let expected_host = local_address.to_string();
    let epoch = Instant::now();
    eprintln!(
        "HeptaBao P0 development server listening on \
         {local_address}; production_supported=false authority=NONE"
    );
    for incoming in listener.incoming() {
        match incoming {
            Ok(mut stream) => {
                if let Err(error) = serve_one(&mut stream, &mut server, epoch, &expected_host) {
                    let response = P0Response {
                        status_code: 400,
                        body: format!("{{\"errors\":[\"{}\"]}}", escape_json(&error)).into_bytes(),
                        committed: false,
                        recovery_reference: None,
                    };
                    let _ = write_response(&mut stream, &response);
                }
            }
            Err(error) => eprintln!("accept failed: {error}"),
        }
    }
    Ok(())
}

fn is_loopback(address: IpAddr) -> bool {
    address.is_loopback()
}

fn serve_one<A: heptabao_p0_server::AuditSink>(
    stream: &mut TcpStream,
    server: &mut P0Server<A>,
    epoch: Instant,
    expected_host: &str,
) -> Result<(), String> {
    stream
        .set_read_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| format!("set read timeout failed: {error}"))?;
    stream
        .set_write_timeout(Some(Duration::from_secs(5)))
        .map_err(|error| format!("set write timeout failed: {error}"))?;
    let received = tick(epoch)?;
    let request = read_request(stream)?;
    if request.headers.get("host") != Some(expected_host) {
        return Err("Host must exactly match the loopback listener address".to_owned());
    }
    let sequence = REQUEST_SEQUENCE.fetch_add(1, Ordering::Relaxed);
    let request_id = RequestId::new(format!("p0-{}-{sequence}", std::process::id()))
        .map_err(|error| error.to_string())?;
    let deadline = MonotonicTick(
        received
            .0
            .checked_add(5_000_000_000)
            .ok_or_else(|| "deadline overflow".to_owned())?,
    );
    let envelope = RequestEnvelope {
        request_id,
        request,
        received_at: received,
        deadline,
    };
    let response = server.handle(envelope, tick(epoch)?);
    write_response(stream, &response)
}

fn read_request(stream: &mut TcpStream) -> Result<heptabao_protocol::ParsedHttpRequest, String> {
    let mut input = Vec::new();
    let mut buffer = [0_u8; 4096];
    loop {
        if input.len() > heptabao_protocol::MAX_HTTP_HEAD_BYTES
            + heptabao_protocol::MAX_HTTP_BODY_BYTES
            + 4
        {
            return Err("request exceeds P0 bounds".to_owned());
        }
        match parse_http_request(&input) {
            Ok(request) => return Ok(request),
            Err(ProtocolError::IncompleteHead | ProtocolError::ContentLengthMismatch) => {}
            Err(error) if !input.is_empty() => return Err(error.to_string()),
            Err(_) => {}
        }
        let count = stream
            .read(&mut buffer)
            .map_err(|error| format!("request read failed: {error}"))?;
        if count == 0 {
            return parse_http_request(&input).map_err(|error| error.to_string());
        }
        input.extend_from_slice(&buffer[..count]);
    }
}

fn write_response(stream: &mut TcpStream, response: &P0Response) -> Result<(), String> {
    let reason = match response.status_code {
        200 => "OK",
        204 => "No Content",
        400 => "Bad Request",
        403 => "Forbidden",
        404 => "Not Found",
        408 => "Request Timeout",
        413 => "Payload Too Large",
        501 => "Not Implemented",
        503 => "Service Unavailable",
        _ => "Error",
    };
    let head = format!(
        concat!(
            "HTTP/1.1 {} {}\r\n",
            "Content-Type: application/json\r\n",
            "Content-Length: {}\r\n",
            "Connection: close\r\n",
            "X-HeptaBao-Profile: HB-P0-DEV-MEMORY\r\n",
            "X-HeptaBao-Production-Supported: false\r\n",
            "\r\n"
        ),
        response.status_code,
        reason,
        response.body.len()
    );
    stream
        .write_all(head.as_bytes())
        .and_then(|()| stream.write_all(&response.body))
        .and_then(|()| stream.flush())
        .map_err(|error| format!("response write failed: {error}"))
}

fn tick(epoch: Instant) -> Result<MonotonicTick, String> {
    let nanos = epoch.elapsed().as_nanos();
    let value = u64::try_from(nanos).map_err(|_| "monotonic tick overflow".to_owned())?;
    Ok(MonotonicTick(value))
}

fn escape_json(value: &str) -> String {
    value
        .replace('\\', "\\\\")
        .replace('"', "\\\"")
        .replace('\n', "\\n")
        .replace('\r', "\\r")
}
