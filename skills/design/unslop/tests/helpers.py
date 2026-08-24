"""Test helpers shared across the unslop suites."""
from __future__ import annotations


def png_bytes(width: int, height: int = 800, pad: int = 9000) -> bytes:
    """A syntactically valid PNG signature + IHDR (real dimensions) padded past the size floor."""
    import struct
    import zlib
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    chunk = b"IHDR" + ihdr
    return b"\x89PNG\r\n\x1a\n" + struct.pack(">I", len(ihdr)) + chunk + struct.pack(">I", zlib.crc32(chunk) & 0xFFFFFFFF) + b"\x00" * pad
