"""Tuya IR code format: FastLZ-compressed µs timings, base64 encoded.

Used by Tuya IR blasters (UFO-R11, ZS06, …), including via Zigbee2MQTT's
`ir_code_to_send`.

Compressor algorithm: mildsunrise
https://gist.github.com/mildsunrise/1d576669b63a260d2cff35fda63ec0b5
"""

from __future__ import annotations

import base64
import io
from bisect import bisect
from struct import pack, unpack


def encode(timings: list[int], freq: int = 38000) -> str:  # noqa: ARG001 - no carrier field in this format
    """Encode raw IR µs durations to a Tuya IR code string."""
    payload = b"".join(pack("<H", min(t, 0xFFFF)) for t in timings)
    buf = io.BytesIO()
    _compress(buf, payload)
    return base64.b64encode(buf.getvalue()).decode()


def decode(code: str) -> list[int]:
    """Decode a Tuya IR code string back to raw µs durations."""
    payload = _decompress(base64.b64decode(code))
    return list(unpack("<" + "H" * (len(payload) // 2), payload))


# ── FastLZ ────────────────────────────────────────────────────────────────────


def _lit_blocks(out: io.BytesIO, data: bytes) -> None:
    for i in range(0, len(data), 32):
        chunk = data[i : i + 32]
        out.write(bytes([len(chunk) - 1]))
        out.write(chunk)


def _dist_block(out: io.BytesIO, length: int, distance: int) -> None:
    distance -= 1
    length -= 2
    block = bytearray()
    if length >= 7:
        block.append(length - 7)
        length = 7
    block.insert(0, length << 5 | distance >> 8)
    block.append(distance & 0xFF)
    out.write(block)


def _compress(out: io.BytesIO, data: bytes) -> None:
    window = 2**13
    max_len = 264
    suffixes: list[int] = []
    next_pos = 0

    def key(n: int) -> bytes:
        return data[n:]

    def find_idx(n: int) -> int:
        return bisect(suffixes, key(n), key=key)

    def candidates(pos: int):
        nonlocal next_pos
        while next_pos <= pos:
            if len(suffixes) == window:
                suffixes.pop(find_idx(next_pos - window))
            suffixes.insert(idx := find_idx(next_pos), next_pos)
            next_pos += 1
        return (pos - suffixes[i] for i in (idx + 1, idx - 1) if 0 <= i < len(suffixes))

    def best_match(pos: int):
        best = None
        for d in candidates(pos):
            n, lim = 0, min(max_len, len(data) - pos)
            while n < lim and data[pos + n] == data[pos - d + n]:
                n += 1
            if n >= 3 and (best is None or n > best[0]):
                best = (n, d)
        return best

    block_start = pos = 0
    while pos < len(data):
        match = best_match(pos)
        if match:
            _lit_blocks(out, data[block_start:pos])
            _dist_block(out, match[0], match[1])
            pos += match[0]
            block_start = pos
        else:
            pos += 1
    _lit_blocks(out, data[block_start:pos])


def _decompress(data: bytes) -> bytes:
    out = bytearray()
    i = 0
    while i < len(data):
        b = data[i]
        if b < 0x20:  # literal run: (b+1) bytes follow
            n = b + 1
            out.extend(data[i + 1 : i + 1 + n])
            i += 1 + n
        else:  # back-reference
            lc = (b >> 5) & 7
            dh = b & 0x1F
            if lc == 7:  # long form: extra length byte before dist_low
                length = 9 + data[i + 1]
                dl = data[i + 2]
                i += 3
            else:
                length = lc + 2
                dl = data[i + 1]
                i += 2
            distance = (dh << 8 | dl) + 1
            pos = len(out)
            for k in range(length):
                out.append(out[pos - distance + k])
    return bytes(out)
