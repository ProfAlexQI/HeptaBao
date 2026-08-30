#!/usr/bin/env python3
"""Execute the exact-head HeptaBao P0 transport and audit matrix.

The runner uses only the Python standard library. It drives the already-started
loopback P0 process, verifies every transport-observable case, and classifies
process-internal deadline, spawn-failure and controlled-drop cases as exact-head
root-unit-gate evidence. Source-marker presence is never counted as runtime PASS.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import struct
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

TOTAL_TIMEOUT_SECONDS = 5.0
MAX_OBSERVED_SECONDS = 8.0
MAX_CONCURRENT_CONNECTIONS = 32
MAX_CLIENT_REQUEST_IDS = 4096
SATURATION_WORKERS = 24


class MatrixFailure(RuntimeError):
    """Raised when one fail-closed transport invariant is not observed."""


@dataclass(frozen=True)
class HttpResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    raw: bytes
    elapsed_seconds: float


def require(condition: bool, message: str) -> None:
    if not condition:
        raise MatrixFailure(message)


def wait_for_address(stderr_path: Path, timeout_seconds: float = 30.0) -> tuple[str, int]:
    deadline = time.monotonic() + timeout_seconds
    pattern = re.compile(r"listening on (127\.0\.0\.1:\d+)")
    while time.monotonic() < deadline:
        text = (
            stderr_path.read_text(encoding="utf-8", errors="replace")
            if stderr_path.exists()
            else ""
        )
        match = pattern.search(text)
        if match:
            host, port_text = match.group(1).rsplit(":", 1)
            return host, int(port_text)
        time.sleep(0.05)
    text = (
        stderr_path.read_text(encoding="utf-8", errors="replace")
        if stderr_path.exists()
        else ""
    )
    raise MatrixFailure(f"P0 listener address was not published: {text[-2000:]}")


def parse_http_response(raw: bytes, elapsed_seconds: float) -> HttpResponse:
    head, separator, body = raw.partition(b"\r\n\r\n")
    require(separator == b"\r\n\r\n", f"response head terminator missing: {raw[:256]!r}")
    lines = head.split(b"\r\n")
    require(bool(lines), "response status line missing")
    status_parts = lines[0].split(b" ", 2)
    require(
        len(status_parts) >= 2 and status_parts[0] == b"HTTP/1.1",
        f"invalid response status line: {lines[0]!r}",
    )
    try:
        status = int(status_parts[1])
    except ValueError as error:
        raise MatrixFailure(f"invalid response status: {lines[0]!r}") from error

    headers: dict[str, str] = {}
    for line in lines[1:]:
        name, colon, value = line.partition(b":")
        require(colon == b":" and bool(name), f"invalid response header: {line!r}")
        key = name.decode("ascii").lower()
        require(key not in headers, f"duplicate response header: {key}")
        headers[key] = value.lstrip(b" ").decode("ascii")
    require("content-length" in headers, "response Content-Length missing")
    try:
        declared = int(headers["content-length"])
    except ValueError as error:
        raise MatrixFailure("response Content-Length is not decimal") from error
    require(declared == len(body), f"response length mismatch: {declared} != {len(body)}")
    return HttpResponse(status, headers, body, raw, elapsed_seconds)


def exchange(host: str, port: int, raw: bytes, timeout_seconds: float = 10.0) -> HttpResponse:
    started = time.monotonic()
    deadline = started + timeout_seconds
    chunks: list[bytes] = []
    with socket.create_connection((host, port), timeout=timeout_seconds) as stream:
        stream.sendall(raw)
        stream.shutdown(socket.SHUT_WR)
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "response read exceeded client-side safety timeout")
            stream.settimeout(remaining)
            try:
                block = stream.recv(8192)
            except socket.timeout as error:
                raise MatrixFailure("response read timed out") from error
            if not block:
                break
            chunks.append(block)
    elapsed = time.monotonic() - started
    return parse_http_response(b"".join(chunks), elapsed)


def request_bytes(
    address: str,
    method: str,
    target: str,
    *,
    body: bytes = b"",
    token: str | None = None,
    request_id: str | None = None,
    extra_headers: list[tuple[str, str]] | None = None,
    include_content_length: bool | None = None,
) -> bytes:
    headers = [f"{method} {target} HTTP/1.1", f"Host: {address}"]
    if token is not None:
        headers.append(f"X-Vault-Token: {token}")
    if request_id is not None:
        headers.append(f"X-HeptaBao-Request-Id: {request_id}")
    if extra_headers:
        headers.extend(f"{name}: {value}" for name, value in extra_headers)
    if include_content_length is None:
        include_content_length = bool(body)
    if include_content_length:
        headers.append(f"Content-Length: {len(body)}")
    return ("\r\n".join(headers) + "\r\n\r\n").encode("ascii") + body


def audit_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def wait_for_audit(
    path: Path,
    start_line: int,
    *,
    detail: str | None = None,
    minimum_new_lines: int = 1,
    timeout_seconds: float = 10.0,
) -> list[str]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        lines = audit_lines(path)
        new_lines = lines[start_line:]
        enough = len(new_lines) >= minimum_new_lines
        matched = detail is None or any(f"detail={detail}" in line for line in new_lines)
        if enough and matched:
            return new_lines
        time.sleep(0.02)
    lines = audit_lines(path)
    raise MatrixFailure(
        f"audit evidence missing detail={detail!r}; new={lines[start_line:start_line + 20]!r}"
    )


def assert_status(response: HttpResponse, expected: int, case_id: str) -> None:
    require(
        response.status == expected,
        f"{case_id}: expected status {expected}, got {response.status}: {response.body[:256]!r}",
    )


def append_case(
    results: list[dict[str, Any]],
    case_id: str,
    evidence: dict[str, Any],
    *,
    status: str = "RUNTIME_PASS",
    evidence_mode: str = "RUNTIME_OBSERVED",
) -> None:
    results.append(
        {
            "case_id": case_id,
            "status": status,
            "evidence_mode": evidence_mode,
            "evidence": evidence,
        }
    )


def trickle_request(host: str, port: int, address: str) -> HttpResponse:
    stream = socket.create_connection((host, port), timeout=10.0)
    started = time.monotonic()
    try:
        stream.settimeout(10.0)
        stream.sendall(
            f"GET /v1/sys/health HTTP/1.1\r\nHost: {address}\r\nX-Trickle: ".encode(
                "ascii"
            )
        )
        for _ in range(12):
            time.sleep(0.4)
            try:
                stream.sendall(b"a")
            except OSError:
                break
        chunks: list[bytes] = []
        deadline = started + MAX_OBSERVED_SECONDS
        while True:
            remaining = deadline - time.monotonic()
            require(remaining > 0, "trickled request exceeded the eight-second matrix bound")
            stream.settimeout(remaining)
            try:
                block = stream.recv(8192)
            except socket.timeout as error:
                raise MatrixFailure("trickled request did not receive a bounded response") from error
            if not block:
                break
            chunks.append(block)
        elapsed = time.monotonic() - started
        return parse_http_response(b"".join(chunks), elapsed)
    finally:
        stream.close()


def fill_request_id_registry(
    host: str,
    port: int,
    address: str,
    existing_ids: int,
) -> tuple[float, set[int]]:
    count = MAX_CLIENT_REQUEST_IDS - existing_ids
    started = time.monotonic()

    def claim(index: int) -> tuple[int, bytes]:
        request_id = f"matrix-saturation-{index:06d}"
        response = exchange(
            host,
            port,
            request_bytes(
                address,
                "GET",
                "/v1/sys/seal-status",
                body=b"x",
                request_id=request_id,
            ),
            timeout_seconds=15.0,
        )
        return response.status, response.body

    statuses: set[int] = set()
    with ThreadPoolExecutor(max_workers=SATURATION_WORKERS) as executor:
        futures = [executor.submit(claim, index) for index in range(count)]
        for future in as_completed(futures):
            status, body = future.result()
            statuses.add(status)
            require(status in {400, 503}, f"registry filler returned unexpected status {status}")
            require(
                b"registry is saturated" not in body,
                "request-ID registry saturated before the declared capacity",
            )
    elapsed = time.monotonic() - started
    require(
        elapsed < 55.0,
        f"request-ID capacity could not be exercised inside its 60-second TTL: {elapsed:.3f}s",
    )
    return elapsed, statuses


def hold_connection(host: str, port: int, address: str) -> socket.socket:
    stream = socket.create_connection((host, port), timeout=5.0)
    stream.settimeout(10.0)
    stream.sendall(
        f"GET /v1/sys/health HTTP/1.1\r\nHost: {address}\r\nX-Hold: ".encode("ascii")
    )
    return stream


def send_reset(host: str, port: int, raw: bytes, settle_seconds: float) -> None:
    stream = socket.create_connection((host, port), timeout=5.0)
    stream.setsockopt(socket.SOL_SOCKET, socket.SO_LINGER, struct.pack("ii", 1, 0))
    try:
        stream.sendall(raw)
        if settle_seconds > 0:
            time.sleep(settle_seconds)
    finally:
        stream.close()


def force_delivery_failure_detail(
    host: str,
    port: int,
    audit_path: Path,
    *,
    detail: str,
    request_factory: Callable[[str], bytes],
    expected_operation: str,
    expected_commit: str,
) -> dict[str, Any]:
    attempts = 0
    label = "before" if expected_commit == "NotCommitted" else "after"
    for settle in (0.0, 0.0002, 0.0005, 0.001, 0.002, 0.004) * 8:
        attempts += 1
        request_id = f"matrix-delivery-{label}-{attempts:04d}"
        start_line = len(audit_lines(audit_path))
        try:
            send_reset(host, port, request_factory(request_id), settle)
        except OSError:
            pass
        deadline = time.monotonic() + 0.15
        while time.monotonic() < deadline:
            lines = audit_lines(audit_path)[start_line:]
            for line in lines:
                if all(
                    token in line
                    for token in (
                        f"request_id={request_id}",
                        f"operation={expected_operation}",
                        f"commit={expected_commit}",
                        f"detail={detail}",
                    )
                ):
                    return {
                        "attempts": attempts,
                        "request_id": request_id,
                        "operation": expected_operation,
                        "commit": expected_commit,
                        "detail": detail,
                    }
            time.sleep(0.005)
    lines = audit_lines(audit_path)
    raise MatrixFailure(
        f"response delivery failure evidence {detail!r} with operation={expected_operation} "
        f"commit={expected_commit} not observed after {attempts} RST attempts; "
        f"tail={lines[-20:]!r}"
    )


def require_root_unit_gate() -> dict[str, str]:
    expected_result = os.environ.get("HEPTABAO_ROOT_GATE_RESULT")
    expected_commit = os.environ.get("HEPTABAO_ROOT_GATE_COMMIT")
    expected_tree = os.environ.get("HEPTABAO_ROOT_GATE_TREE")
    require(expected_result == "success", "exact-head root unit gate did not succeed")
    require(bool(expected_commit), "exact-head root unit gate commit is missing")
    require(bool(expected_tree), "exact-head root unit gate tree is missing")
    actual_commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], text=True
    ).strip()
    actual_tree = subprocess.check_output(
        ["git", "rev-parse", "HEAD^{tree}"], text=True
    ).strip()
    require(
        actual_commit == expected_commit,
        f"root unit gate commit drift: {expected_commit} != {actual_commit}",
    )
    require(
        actual_tree == expected_tree,
        f"root unit gate tree drift: {expected_tree} != {actual_tree}",
    )
    return {
        "root_gate_result": expected_result,
        "root_gate_commit": actual_commit,
        "root_gate_tree": actual_tree,
    }


def execute(args: argparse.Namespace) -> dict[str, Any]:
    stderr_path = args.stderr.resolve()
    audit_path = args.audit.resolve()
    token = os.environ.get("HEPTABAO_P0_DEV_TOKEN")
    unseal_key = os.environ.get("HEPTABAO_P0_DEV_UNSEAL_KEY")
    require(bool(token), "HEPTABAO_P0_DEV_TOKEN is required by the matrix")
    require(bool(unseal_key), "HEPTABAO_P0_DEV_UNSEAL_KEY is required by the matrix")

    host, port = wait_for_address(stderr_path)
    address = f"{host}:{port}"
    results: list[dict[str, Any]] = []
    observed_response_seconds: list[float] = []

    start = len(audit_lines(audit_path))
    health = exchange(host, port, request_bytes(address, "GET", "/v1/sys/health"))
    assert_status(health, 501, "P0-TRANSPORT-001")
    observed_response_seconds.append(health.elapsed_seconds)
    lines = wait_for_audit(audit_path, start, minimum_new_lines=2)
    require(any("phase=RequestAccepted" in line for line in lines), "health acceptance audit missing")
    require(any("phase=ResponsePrepared" in line for line in lines), "health response audit missing")
    append_case(
        results,
        "P0-TRANSPORT-001",
        {"status": 501, "audit_events": 2, "elapsed_seconds": round(health.elapsed_seconds, 6)},
    )

    start = len(audit_lines(audit_path))
    duplicate = exchange(
        host,
        port,
        (
            f"GET /v1/sys/health HTTP/1.1\r\nHost: {address}\r\nhost: {address}\r\n\r\n"
        ).encode("ascii"),
    )
    assert_status(duplicate, 400, "P0-TRANSPORT-002")
    observed_response_seconds.append(duplicate.elapsed_seconds)
    wait_for_audit(audit_path, start, detail="protocol-duplicate-header")
    append_case(results, "P0-TRANSPORT-002", {"status": 400, "detail": "protocol-duplicate-header"})

    start = len(audit_lines(audit_path))
    mismatch = exchange(
        host,
        port,
        b"GET /v1/sys/health HTTP/1.1\r\nHost: 127.0.0.1:1\r\n\r\n",
    )
    assert_status(mismatch, 400, "P0-TRANSPORT-003")
    observed_response_seconds.append(mismatch.elapsed_seconds)
    wait_for_audit(audit_path, start, detail="host-listener-mismatch")
    append_case(results, "P0-TRANSPORT-003", {"status": 400, "detail": "host-listener-mismatch"})

    start = len(audit_lines(audit_path))
    trickled = trickle_request(host, port, address)
    assert_status(trickled, 408, "P0-TRANSPORT-004")
    require(
        trickled.elapsed_seconds <= MAX_OBSERVED_SECONDS,
        f"trickled request exceeded {MAX_OBSERVED_SECONDS}s: {trickled.elapsed_seconds:.3f}s",
    )
    wait_for_audit(audit_path, start, detail="request-read-deadline-exceeded")
    append_case(
        results,
        "P0-TRANSPORT-004",
        {
            "status": 408,
            "detail": "request-read-deadline-exceeded",
            "elapsed_seconds": round(trickled.elapsed_seconds, 6),
        },
    )

    initialized = exchange(
        host,
        port,
        request_bytes(address, "POST", "/v1/sys/init", body=b"{}"),
    )
    assert_status(initialized, 200, "matrix setup init")

    replay_id = "matrix-replay-request-0001"
    first = exchange(
        host,
        port,
        request_bytes(
            address,
            "GET",
            "/v1/sys/seal-status",
            request_id=replay_id,
        ),
    )
    assert_status(first, 200, "P0-TRANSPORT-005 first")
    start = len(audit_lines(audit_path))
    second = exchange(
        host,
        port,
        request_bytes(
            address,
            "GET",
            "/v1/sys/seal-status",
            request_id=replay_id,
        ),
    )
    assert_status(second, 409, "P0-TRANSPORT-005 replay")
    wait_for_audit(audit_path, start, detail="client-request-id-replayed")
    append_case(
        results,
        "P0-TRANSPORT-005",
        {"first_status": 200, "second_status": 409, "detail": "client-request-id-replayed"},
    )

    fill_elapsed, filler_statuses = fill_request_id_registry(host, port, address, existing_ids=1)
    start = len(audit_lines(audit_path))
    saturated = exchange(
        host,
        port,
        request_bytes(
            address,
            "GET",
            "/v1/sys/seal-status",
            request_id="matrix-saturation-overflow-0001",
        ),
    )
    assert_status(saturated, 503, "P0-TRANSPORT-006")
    require(b"registry is saturated" in saturated.body, "saturation response reason drift")
    wait_for_audit(audit_path, start, detail="request-id-registry-saturated")
    append_case(
        results,
        "P0-TRANSPORT-006",
        {
            "status": 503,
            "detail": "request-id-registry-saturated",
            "declared_capacity": MAX_CLIENT_REQUEST_IDS,
            "fill_elapsed_seconds": round(fill_elapsed, 6),
            "filler_statuses": sorted(filler_statuses),
        },
    )

    held: list[socket.socket] = []
    try:
        for _ in range(MAX_CONCURRENT_CONNECTIONS):
            held.append(hold_connection(host, port, address))
        time.sleep(0.25)
        start = len(audit_lines(audit_path))
        capacity = exchange(host, port, request_bytes(address, "GET", "/v1/sys/health"))
        assert_status(capacity, 429, "P0-TRANSPORT-007")
        observed_response_seconds.append(capacity.elapsed_seconds)
        wait_for_audit(audit_path, start, detail="connection-capacity-exhausted")
    finally:
        for stream in held:
            try:
                stream.close()
            except OSError:
                pass
    release_deadline = time.monotonic() + 10.0
    release_resets = 0
    while True:
        require(time.monotonic() < release_deadline, "connection admission capacity was not released")
        try:
            probe = exchange(
                host, port, request_bytes(address, "GET", "/v1/sys/seal-status")
            )
        except (ConnectionResetError, BrokenPipeError):
            release_resets += 1
            time.sleep(0.05)
            continue
        if probe.status != 429:
            require(probe.status == 200, f"capacity-release probe returned {probe.status}")
            break
        time.sleep(0.05)
    append_case(
        results,
        "P0-TRANSPORT-007",
        {
            "status": 429,
            "detail": "connection-capacity-exhausted",
            "limit": 32,
            "capacity_release_resets": release_resets,
        },
    )

    unseal_body = json.dumps({"key": unseal_key}, separators=(",", ":")).encode("ascii")
    unsealed = exchange(
        host,
        port,
        request_bytes(address, "POST", "/v1/sys/unseal", body=unseal_body),
    )
    assert_status(unsealed, 200, "matrix setup unseal")

    write_body = b'{"value":"matrix-alpha"}'
    no_content = exchange(
        host,
        port,
        request_bytes(
            address,
            "POST",
            "/v1/secret/matrix/no-content",
            body=write_body,
            token=token,
        ),
    )
    assert_status(no_content, 204, "P0-TRANSPORT-008")
    require(no_content.headers.get("content-length") == "0", "204 Content-Length is not zero")
    require(no_content.body == b"", "204 emitted body bytes")
    append_case(results, "P0-TRANSPORT-008", {"status": 204, "content_length": 0, "body_bytes": 0})

    start = len(audit_lines(audit_path))
    malformed = exchange(
        host,
        port,
        (
            f"POST /v1/sys/init HTTP/1.1\r\nHost: {address}\r\n"
            "Transfer-Encoding: chunked\r\n\r\n"
        ).encode("ascii"),
    )
    assert_status(malformed, 400, "P0-TRANSPORT-009")
    observed_response_seconds.append(malformed.elapsed_seconds)
    wait_for_audit(audit_path, start, detail="protocol-transfer-encoding-forbidden")
    append_case(
        results,
        "P0-TRANSPORT-009",
        {"status": 400, "detail": "protocol-transfer-encoding-forbidden"},
    )

    large_value = b"x" * 60_000
    large_body = b'{"value":"' + large_value + b'"}'
    primed = exchange(
        host,
        port,
        request_bytes(
            address,
            "POST",
            "/v1/secret/matrix/delivery",
            body=large_body,
            token=token,
        ),
        timeout_seconds=15.0,
    )
    assert_status(primed, 204, "matrix setup large secret")
    before_delivery = force_delivery_failure_detail(
        host,
        port,
        audit_path,
        detail="response-delivery-failed-before-commit",
        request_factory=lambda request_id: request_bytes(
            address,
            "GET",
            "/v1/secret/matrix/delivery",
            token=token,
            request_id=request_id,
        ),
        expected_operation="KvRead",
        expected_commit="NotCommitted",
    )
    after_delivery = force_delivery_failure_detail(
        host,
        port,
        audit_path,
        detail="response-delivery-failed-after-commit",
        request_factory=lambda request_id: request_bytes(
            address,
            "POST",
            "/v1/secret/matrix/delivery",
            body=large_body,
            token=token,
            request_id=request_id,
        ),
        expected_operation="KvWrite",
        expected_commit="Committed",
    )
    append_case(
        results,
        "P0-TRANSPORT-010",
        {
            "details": [
                "response-delivery-failed-before-commit",
                "response-delivery-failed-after-commit",
            ],
            "before_commit": before_delivery,
            "after_commit": after_delivery,
        },
    )

    maximum_response = max(observed_response_seconds)
    require(
        maximum_response < TOTAL_TIMEOUT_SECONDS,
        f"immediate response exceeded the five-second write lifetime: {maximum_response:.3f}s",
    )
    root_unit_gate = require_root_unit_gate()
    append_case(
        results,
        "P0-TRANSPORT-011",
        {
            **root_unit_gate,
            "unit_test": (
                "heptabao-p0-server(bin)::tests::"
                "partial_write_progress_cannot_reset_absolute_deadline"
            ),
            "maximum_immediate_response_seconds": round(maximum_response, 6),
        },
        status="UNIT_GATE_PASS",
        evidence_mode="EXACT_HEAD_ROOT_UNIT_GATE",
    )

    append_case(
        results,
        "P0-TRANSPORT-012",
        {
            **root_unit_gate,
            "unit_test": (
                "heptabao-p0-server(bin)::tests::"
                "worker_spawn_failure_releases_capacity_and_is_audited"
            ),
        },
        status="UNIT_GATE_PASS",
        evidence_mode="EXACT_HEAD_ROOT_UNIT_GATE",
    )

    start = len(audit_lines(audit_path))
    ignored = exchange(
        host,
        port,
        request_bytes(
            address,
            "GET",
            "/v1/sys/seal-status",
            body=b"x",
        ),
    )
    assert_status(ignored, 400, "P0-TRANSPORT-013 ignored body")
    new_lines = wait_for_audit(audit_path, start, detail="operation-body-forbidden")
    require(
        not any("phase=RequestAccepted" in line for line in new_lines),
        "ignored operation body reached request acceptance",
    )
    non_exact_init = exchange(
        host,
        port,
        request_bytes(address, "POST", "/v1/sys/init", body=b'{"x":1}'),
    )
    assert_status(non_exact_init, 400, "P0-TRANSPORT-013 non-exact init")
    append_case(
        results,
        "P0-TRANSPORT-013",
        {"status": 400, "detail": "operation-body-forbidden", "dispatch": False},
    )

    append_case(
        results,
        "P0-TRANSPORT-014",
        {
            **root_unit_gate,
            "unit_tests": [
                "heptabao-protocol::tests::canonical_target_drop_executes_zeroizing_path",
                "heptabao-p0-server::tests::secret_path_drop_executes_zeroizing_path",
            ],
            "qualification_effect": "NONE",
        },
        status="UNIT_GATE_PASS",
        evidence_mode="EXACT_HEAD_ROOT_UNIT_GATE",
    )

    require(len(results) == 14, f"matrix result count drift: {len(results)}")
    require(
        sum(case["status"] == "RUNTIME_PASS" for case in results) == 11,
        "runtime-observed case count drift",
    )
    require(
        sum(case["status"] == "UNIT_GATE_PASS" for case in results) == 3,
        "exact-head root-unit-gate case count drift",
    )
    return {
        "schema": "heptabao.p0-transport-exact-result.v2",
        "source": {
            "repository": os.environ.get("GITHUB_REPOSITORY", "unknown"),
            "commit": os.environ.get("SOURCE_SHA") or os.environ.get("GITHUB_SHA", "unknown"),
        },
        "profile": "HB-P0-DEV-MEMORY",
        "server": {"loopback": True, "port": port},
        "result": "PASS",
        "counts": {
            "runtime_pass": sum(case["status"] == "RUNTIME_PASS" for case in results),
            "unit_gate_pass": sum(case["status"] == "UNIT_GATE_PASS" for case in results),
            "total_pass": len(results),
            "fail": 0,
            "blocked": 0,
            "unexecuted": 0,
        },
        "cases": results,
        "audit_line_count": len(audit_lines(audit_path)),
        "qualification": False,
        "compatibility_claim": False,
        "authority_effect": "NONE",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stderr", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = execute(args)
    except (MatrixFailure, OSError, ValueError, subprocess.CalledProcessError) as error:
        report = {
            "schema": "heptabao.p0-transport-exact-result.v2",
            "result": "FAIL",
            "reason": str(error),
            "qualification": False,
            "compatibility_claim": False,
            "authority_effect": "NONE",
        }
        print(json.dumps(report, sort_keys=True, separators=(",", ":")))
        return 1
    print(json.dumps(report, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
