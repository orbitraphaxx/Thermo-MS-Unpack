#!/usr/bin/env python3
"""tnga_decode.py -- decode TNGA-encrypted ICL files (.lub/.xmb/.jsob).

Covers the Lua control library on the TNG platform (Stellar, TSQ Series II) and
the .xmb/.jsob device, tune and calibration configs shipped with current Orbitraps
(Astral, Exploris, Tribrid). AES-256-CBC; the key and IV are static data in the
host TNGEnc.dll, so supply your own copy from an installation you have. The DLL
is read as data and never loaded, and no decoded file is executed.

Usage:
    python tnga_decode.py TNGEnc.dll library.lub OUT_DIR
    python tnga_decode.py TNGEnc.dll icl_encrypted/ OUT_DIR
"""

import argparse
import hashlib
import json
from pathlib import Path
import struct

import pefile
from Crypto.Cipher import AES
from Crypto.Util.Padding import unpad

HEADER = b"TNGA\x00\x00\x00\x01"
SUFFIX = {".lub": ".lua", ".xmb": ".xml", ".jsob": ".json"}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def parameters(dll):
    """Candidate (key, iv) pairs from the DLL's constant data.

    The 32-byte key and 16-byte IV sit just below the header constant, in that
    order. Wrong candidates fail the padding and length checks in decode().
    """
    pe = pefile.PE(str(dll))
    try:
        image = pe.get_memory_mapped_image()
        found, at = [], image.find(HEADER)
        while at >= 0:
            if at >= 0x38:
                found.append((image[at - 0x28:at - 8], image[at - 0x38:at - 0x28]))
            at = image.find(HEADER, at + 1)
        return found
    finally:
        pe.close()


def decode(data, key, iv):
    if len(data) < 28 or data[:8] != HEADER:
        raise ValueError("unsupported or truncated TNGA header")
    length = struct.unpack_from("<I", data, 8)[0]
    body = data[12:]
    if len(body) % 16 or len(body) != (length // 16 + 1) * 16:
        raise ValueError("ciphertext size disagrees with declared length and padding")
    plain = unpad(AES.new(key, AES.MODE_CBC, iv).decrypt(body), 16, style="pkcs7")
    if len(plain) != length:
        raise ValueError("decoded size disagrees with declared length")
    return plain


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dll", type=Path, help="TNGEnc.dll from the instrument host software")
    ap.add_argument("source", type=Path, help="One encrypted file, or a directory to walk")
    ap.add_argument("output", type=Path, help="New directory (must not already exist)")
    a = ap.parse_args()

    walk = a.source.is_dir()
    paths = sorted(p for p in a.source.rglob("*") if p.suffix.lower() in SUFFIX) if walk else [a.source]
    if not paths:
        ap.error(f"no {'/'.join(SUFFIX)} inputs under {a.source}")
    key = iv = None
    for candidate in parameters(a.dll):
        try:
            decode(paths[0].read_bytes(), *candidate)
        except ValueError:
            continue
        key, iv = candidate
        break
    if key is None:
        raise SystemExit(f"no key/IV in {a.dll} decodes {paths[0].name}")

    a.output.mkdir(parents=True, exist_ok=False)
    records = []
    for src in paths:
        relative = src.relative_to(a.source) if walk else Path(src.name)
        data = src.read_bytes()
        plain = decode(data, key, iv)
        bytecode = plain.startswith(b"\x1bLua")
        target = a.output / relative.with_suffix(".luac" if bytecode else SUFFIX[src.suffix.lower()])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(plain)
        records.append({"input": relative.as_posix(), "source_bytes": len(data),
                        "source_sha256": digest(data),
                        "output": target.relative_to(a.output).as_posix(),
                        "plaintext_bytes": len(plain), "plaintext_sha256": digest(plain),
                        "representation": "lua-bytecode" if bytecode else "text",
                        "padding_valid": True, "length_valid": True})
    manifest = {"dll": a.dll.name, "dll_sha256": digest(a.dll.read_bytes()),
                "cipher": "AES-256-CBC", "padding": "PKCS7",
                "header_hex": HEADER.hex(), "files": records}
    (a.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"{len(records)} files decoded; padding and declared lengths valid")


if __name__ == "__main__":
    main()
