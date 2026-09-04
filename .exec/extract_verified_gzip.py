#!/usr/bin/env python3
"""Recover one gzip member while binding the exact uncompressed payload.

The V1.9 external-admission payload was committed with a damaged gzip trailer.
This helper never trusts that trailer: it parses the header, requires a complete
single DEFLATE stream, rejects extra members/trailing bytes, and admits output
only when its SHA-256 equals the immutable expected source digest.
"""
from __future__ import annotations

import argparse
import binascii
import hashlib
import struct
import sys
import zlib
from pathlib import Path


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def consume_c_string(data: bytes, offset: int, field: str) -> int:
    end = data.find(b"\x00", offset)
    if end < 0:
        fail(f"gzip {field} is unterminated")
    return end + 1


def deflate_offset(data: bytes) -> int:
    if len(data) < 18:
        fail("gzip payload is too short")
    if data[:2] != b"\x1f\x8b":
        fail("gzip magic mismatch")
    if data[2] != 8:
        fail(f"unsupported gzip compression method: {data[2]}")
    flags = data[3]
    if flags & 0xE0:
        fail(f"gzip reserved flags are set: 0x{flags:02x}")

    offset = 10
    if flags & 0x04:  # FEXTRA
        if offset + 2 > len(data):
            fail("gzip extra-field length is truncated")
        extra_length = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2 + extra_length
        if offset > len(data):
            fail("gzip extra field is truncated")
    if flags & 0x08:  # FNAME
        offset = consume_c_string(data, offset, "filename")
    if flags & 0x10:  # FCOMMENT
        offset = consume_c_string(data, offset, "comment")
    if flags & 0x02:  # FHCRC
        offset += 2
        if offset > len(data):
            fail("gzip header CRC is truncated")
    return offset


def extract(data: bytes) -> tuple[bytes, int, int, int, int]:
    offset = deflate_offset(data)
    decoder = zlib.decompressobj(-zlib.MAX_WBITS)
    output = decoder.decompress(data[offset:]) + decoder.flush()
    if not decoder.eof:
        fail("gzip DEFLATE stream did not reach an end marker")
    trailer = decoder.unused_data
    if len(trailer) != 8:
        fail(
            "expected exactly one eight-byte gzip trailer; "
            f"found {len(trailer)} trailing bytes"
        )
    stored_crc, stored_size = struct.unpack("<II", trailer)
    actual_crc = binascii.crc32(output) & 0xFFFFFFFF
    actual_size = len(output) & 0xFFFFFFFF
    return output, stored_crc, stored_size, actual_crc, actual_size


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--sha256", required=True)
    args = parser.parse_args()

    expected = args.sha256.lower()
    if len(expected) != 64 or any(char not in "0123456789abcdef" for char in expected):
        fail("expected SHA-256 must be 64 lowercase hexadecimal characters")

    payload, stored_crc, stored_size, actual_crc, actual_size = extract(
        args.input.read_bytes()
    )
    digest = hashlib.sha256(payload).hexdigest()
    if digest != expected:
        fail(f"uncompressed payload SHA-256 mismatch: {digest} != {expected}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    print(
        "verified gzip payload: "
        f"sha256={digest} bytes={len(payload)} "
        f"trailer_crc_match={stored_crc == actual_crc} "
        f"trailer_size_match={stored_size == actual_size}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
