"""Little-endian bitfield view over a byte array.

Lets a protocol mirror an IRremoteESP8266 `union …Protocol` struct field for
field, so the C header stays the readable spec.

C bitfields on a little-endian target pack from the least significant bit of
each storage unit, which over a byte array is one continuous LSB-first bit
stream: so a field is addressed by (byte, bit-within-byte, width).
"""

from __future__ import annotations


class Field:
    """One bitfield of `width` bits starting at `bit` of `byte`."""

    __slots__ = ("_mask", "_shift", "width")

    def __init__(self, byte: int, bit: int = 0, width: int = 1) -> None:
        self.width = width
        self._shift = byte * 8 + bit
        self._mask = (1 << width) - 1

    def __get__(self, obj: RawState | None, _owner: type | None = None):
        if obj is None:
            return self
        return (int.from_bytes(obj.raw, "little") >> self._shift) & self._mask

    def __set__(self, obj: RawState, value: int) -> None:
        # Rebuilds the whole packed int from `obj.raw` on every write instead of
        # patching bytes in place. Frames are <64 bytes and each field is set only
        # a handful of times per command, so the O(n) cost is negligible.
        packed = int.from_bytes(obj.raw, "little")
        packed &= ~(self._mask << self._shift)
        packed |= (int(value) & self._mask) << self._shift
        obj.raw[:] = packed.to_bytes(len(obj.raw), "little")


class RawState:
    """Base for a fixed-length frame addressed through `Field` descriptors."""

    LENGTH: int = 0

    def __init__(self, raw: bytes | bytearray | None = None) -> None:
        self.raw = bytearray(raw if raw is not None else self.LENGTH)
        if len(self.raw) != self.LENGTH:
            raise ValueError(f"expected {self.LENGTH} bytes, got {len(self.raw)}")

    def hex(self) -> str:
        return " ".join(f"{b:02X}" for b in self.raw)
