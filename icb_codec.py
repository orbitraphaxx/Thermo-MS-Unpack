#!/usr/bin/env python3
"""
icb_codec.py -- decode / encode Thermo ITCL *.ICB files.

Usage:
    python3 icb_codec.py decode mxinit.ICB  mxinit.itcl
    python3 icb_codec.py encode mxinit.itcl mxinit.ICB
"""

import struct
import sys

MAGIC = bytes.fromhex("ab0001dc")


def transform(payload: bytes, offset: int = 8) -> bytes:
    """XOR 0x01 over bytes sitting at even absolute file offsets."""
    b = bytearray(payload)
    for i in range(len(b)):
        if (i + offset) % 2 == 0:
            b[i] ^= 1
    return bytes(b)


def decode(raw: bytes) -> bytes:
    if raw[:4] != MAGIC:
        raise ValueError(f"bad magic {raw[:4].hex()}, expected {MAGIC.hex()}")
    declared = struct.unpack("<I", raw[4:8])[0]
    if declared != len(raw):
        print(f"warning: header says {declared} bytes, file is {len(raw)}",
              file=sys.stderr)
    return transform(raw[8:])


def encode(src: bytes) -> bytes:
    return MAGIC + struct.pack("<I", len(src) + 8) + transform(src)


if __name__ == "__main__":
    mode, inp, outp = sys.argv[1], sys.argv[2], sys.argv[3]
    data = open(inp, "rb").read()
    open(outp, "wb").write(decode(data) if mode == "decode" else encode(data))
