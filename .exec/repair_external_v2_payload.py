#!/usr/bin/env python3
"""Deterministically recover and replace the damaged V1.9 external-V2 payload.

The committed gzip member contains one corrupt DEFLATE back-reference byte.  A
single-byte correction makes the stream complete, but that back-reference emits
`cti` where the exact source used `ope`.  The replacements below are limited to
those resulting lexical forms.  Recovery is admitted only when the reconstructed
source matches the pre-existing SHA-256, gzip CRC32 and uncompressed-size tuple.
"""
from __future__ import annotations

import argparse
import base64
import binascii
import gzip
import hashlib
import io
import struct
import zlib
from pathlib import Path

PAYLOAD_PATH = Path(".exec/augment_external_v2.py.gz.b64")
CORRUPT_GZIP_SHA256 = "71afc5ffae0624053a59b412cd50289401c976a2f352eead3f882bf2e2470df6"
CORRUPT_GZIP_SIZE = 8818
CORRUPT_BYTE_OFFSET = 1964
RECOVERY_BYTE = 178
EXPECTED_SOURCE_SHA256 = "c97528017a6b4cb22acd32cd191fb88f26f5697015fb75035176ccb5ec98716b"
EXPECTED_SOURCE_CRC32 = 0xF4B635B9
EXPECTED_SOURCE_SIZE = 33888

# Apply longer forms first so each replacement is unambiguous and bounded.
RECOVERY_REPLACEMENTS = (
    (b"envelctis", b"envelopes"),
    (b"envelcti", b"envelope"),
    (b"scctid", b"scoped"),
    (b"sccti", b"scope"),
    (b"remains ctin", b"remains open"),
    (b"ctinssl", b"openssl"),
)


def fail(message: str) -> "NoReturn":
    raise SystemExit(message)


def deflate_offset(data: bytes) -> int:
    if len(data) < 18 or data[:3] != b"\x1f\x8b\x08":
        fail("payload is not one gzip/DEFLATE member")
    flags = data[3]
    if flags & 0xE0:
        fail("gzip reserved flags are set")
    offset = 10
    if flags & 0x04:
        if offset + 2 > len(data):
            fail("truncated gzip extra-field length")
        extra_length = int.from_bytes(data[offset : offset + 2], "little")
        offset += 2 + extra_length
    for flag, label in ((0x08, "filename"), (0x10, "comment")):
        if flags & flag:
            end = data.find(b"\x00", offset)
            if end < 0:
                fail(f"unterminated gzip {label}")
            offset = end + 1
    if flags & 0x02:
        offset += 2
    if offset >= len(data) - 8:
        fail("gzip header consumes the member")
    return offset


def recover_source(encoded: bytes) -> bytes:
    compact = b"".join(encoded.split())
    try:
        damaged = bytearray(base64.b64decode(compact, validate=True))
    except (ValueError, binascii.Error) as error:
        fail(f"payload base64 is invalid: {error}")
    if len(damaged) != CORRUPT_GZIP_SIZE:
        fail(f"unexpected damaged gzip size: {len(damaged)}")
    observed = hashlib.sha256(damaged).hexdigest()
    if observed != CORRUPT_GZIP_SHA256:
        fail(f"damaged gzip identity drifted: {observed}")
    if damaged[CORRUPT_BYTE_OFFSET] == RECOVERY_BYTE:
        fail("payload already contains the recovery byte but is not canonical")
    damaged[CORRUPT_BYTE_OFFSET] = RECOVERY_BYTE

    offset = deflate_offset(damaged)
    stored_crc, stored_size = struct.unpack("<II", damaged[-8:])
    if stored_crc != EXPECTED_SOURCE_CRC32 or stored_size != EXPECTED_SOURCE_SIZE:
        fail("committed gzip trailer no longer matches the frozen recovery tuple")
    try:
        candidate = zlib.decompress(bytes(damaged[offset:-8]), -zlib.MAX_WBITS)
    except zlib.error as error:
        fail(f"corrected DEFLATE stream is invalid: {error}")
    if len(candidate) != EXPECTED_SOURCE_SIZE:
        fail(f"corrected stream length mismatch: {len(candidate)}")

    recovered = candidate
    for damaged_form, original_form in RECOVERY_REPLACEMENTS:
        count = recovered.count(damaged_form)
        if count == 0:
            fail(f"expected damaged lexical form is absent: {damaged_form!r}")
        recovered = recovered.replace(damaged_form, original_form)
    for damaged_form, _ in RECOVERY_REPLACEMENTS:
        if damaged_form in recovered:
            fail(f"damaged lexical form remains after recovery: {damaged_form!r}")

    digest = hashlib.sha256(recovered).hexdigest()
    crc = binascii.crc32(recovered) & 0xFFFFFFFF
    if digest != EXPECTED_SOURCE_SHA256:
        fail(f"recovered source SHA-256 mismatch: {digest}")
    if crc != EXPECTED_SOURCE_CRC32 or len(recovered) != EXPECTED_SOURCE_SIZE:
        fail("recovered source CRC/size mismatch")
    compile(recovered.decode("utf-8"), "augment_external_v2.py", "exec")
    return recovered


def canonical_payload(source: bytes) -> bytes:
    output = io.BytesIO()
    with gzip.GzipFile(
        filename="augment_external_v2.py",
        mode="wb",
        fileobj=output,
        compresslevel=9,
        mtime=0,
    ) as archive:
        archive.write(source)
    payload = output.getvalue()
    if gzip.decompress(payload) != source:
        fail("canonical gzip round-trip failed")
    return base64.b64encode(payload) + b"\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=PAYLOAD_PATH)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()

    source = recover_source(args.path.read_bytes())
    encoded = canonical_payload(source)
    if args.write:
        args.path.write_bytes(encoded)
    print(
        "PASS recovered external V2 payload "
        f"source_sha256={hashlib.sha256(source).hexdigest()} "
        f"source_crc32={binascii.crc32(source) & 0xFFFFFFFF:08x} "
        f"source_bytes={len(source)} canonical_base64_bytes={len(encoded)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
