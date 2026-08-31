#!/usr/bin/env python3
"""RST-tolerant entrypoint for the exact-head P0 transport matrix.

The immutable matrix implementation is retained in
``p0_transport_exact_core_v1``.  This entrypoint changes only client-side
response collection: a TCP reset is accepted as end-of-stream only after a
complete HTTP response has already been received.  A reset before any response
bytes, or a partial/malformed response followed by reset, remains a fail-closed
matrix failure.
"""

from __future__ import annotations

import errno
import socket
import time
from typing import Protocol

import p0_transport_exact_core_v1 as core
from p0_transport_exact_core_v1 import *  # noqa: F403 - preserve the v1 public test surface


class _ReadableSocket(Protocol):
    def settimeout(self, value: float) -> None: ...

    def recv(self, size: int) -> bytes: ...


def _is_reset(error: OSError) -> bool:
    return isinstance(error, (ConnectionResetError, BrokenPipeError)) or error.errno in {
        errno.ECONNRESET,
        errno.EPIPE,
        errno.ENOTCONN,
    }


def _read_response(
    stream: _ReadableSocket,
    *,
    started: float,
    deadline: float,
    timeout_message: str,
    reset_message: str,
) -> core.HttpResponse:
    chunks: list[bytes] = []
    while True:
        remaining = deadline - time.monotonic()
        core.require(remaining > 0, timeout_message)
        stream.settimeout(remaining)
        try:
            block = stream.recv(8192)
        except socket.timeout as error:
            raise core.MatrixFailure(timeout_message) from error
        except OSError as error:
            if not _is_reset(error):
                raise
            if not chunks:
                raise core.MatrixFailure(reset_message) from error
            # Linux may deliver a complete response followed by ECONNRESET when
            # the peer closes with unread ingress.  Treat the reset as EOF only
            # after bytes exist; parse_http_response below still rejects a
            # partial head, partial body, duplicate header or length mismatch.
            break
        if not block:
            break
        chunks.append(block)
    elapsed = time.monotonic() - started
    return core.parse_http_response(b"".join(chunks), elapsed)


def exchange(
    host: str,
    port: int,
    raw: bytes,
    timeout_seconds: float = 10.0,
) -> core.HttpResponse:
    started = time.monotonic()
    deadline = started + timeout_seconds
    with socket.create_connection((host, port), timeout=timeout_seconds) as stream:
        try:
            stream.sendall(raw)
        except OSError as error:
            if _is_reset(error):
                raise core.MatrixFailure(
                    "request connection reset before the request was delivered"
                ) from error
            raise
        try:
            stream.shutdown(socket.SHUT_WR)
        except OSError as error:
            if not _is_reset(error):
                raise
        return _read_response(
            stream,
            started=started,
            deadline=deadline,
            timeout_message="response read exceeded client-side safety timeout",
            reset_message="response connection reset before any response bytes",
        )


def trickle_request(host: str, port: int, address: str) -> core.HttpResponse:
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
            except OSError as error:
                if _is_reset(error):
                    break
                raise
        return _read_response(
            stream,
            started=started,
            deadline=started + core.MAX_OBSERVED_SECONDS,
            timeout_message="trickled request exceeded the eight-second matrix bound",
            reset_message="trickled request reset before any response bytes",
        )
    finally:
        stream.close()


# The core functions resolve these names from their defining module globals.
# Patch those exact globals before exposing the inherited CLI and tests.
core.exchange = exchange
core.trickle_request = trickle_request


if __name__ == "__main__":
    raise SystemExit(core.main())
