#!/usr/bin/env python3
r"""
msx_codec.py -- decode / encode Thermo Exactive-series instrument files.

Covers every file in  ...\Exactive\instrument_current\msx_instrument_files\ :

    *.mstune          tune file          -> Prometheus XML
    *.mscal           calibration file   -> Prometheus XML
    inst_config.cfg   instrument config  -> Python literal dict
    procedure_history procedure results  -> Python literal dict

Usage:
    python msx_codec.py decode master_cal.mscal cal.xml
    python msx_codec.py dump   inst_config.cfg          # pretty-print to stdout
    python msx_codec.py encode cal.xml master_cal.mscal --from master_cal.mscal
"""

import argparse
import io
import os
import sys
import zipfile

KEY = 0x51


def unmask(data: bytes) -> bytes:
    """XOR 0x51 over every byte. Its own inverse."""
    return bytes(b ^ KEY for b in data)


mask = unmask  # same operation


def _split_prefix(raw: bytes):
    """Return (prefix, zipbytes). Some files carry a couple of leading bytes."""
    plain = unmask(raw)
    i = plain.find(b"PK\x03\x04")
    if i < 0:
        raise ValueError("no ZIP local-file header found after XOR 0x51")
    return plain[:i], plain[i:]


def decode(raw: bytes):
    """Return (payload_bytes, checksum_bytes, prefix_bytes)."""
    prefix, zbytes = _split_prefix(raw)
    with zipfile.ZipFile(io.BytesIO(zbytes)) as z:
        names = z.namelist()
        if "payload" not in names:
            raise ValueError(f"expected a 'payload' entry, got {names}")
        payload = z.read("payload")
        checksum = z.read("checksum") if "checksum" in names else b""
    return payload, checksum, prefix


def encode(payload: bytes, checksum: bytes, prefix: bytes = b"") -> bytes:
    """Rebuild a masked container. See the checksum caveat in the module docstring."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("payload", payload)
        if checksum:
            z.writestr("checksum", checksum)
    return mask(prefix + buf.getvalue())


def _pretty(payload: bytes) -> str:
    text = payload.decode("utf-8", "replace")
    if text.lstrip().startswith("<?xml"):
        import xml.dom.minidom
        return xml.dom.minidom.parseString(text).toprettyxml(indent="  ")
    # Python literal (inst_config.cfg, procedure_history). These are Python 2
    # reprs and may contain u'...' literals, which ast.literal_eval handles.
    try:
        import ast
        import pprint
        return pprint.pformat(ast.literal_eval(text), width=100)
    except Exception:
        return text


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["decode", "encode", "dump"])
    ap.add_argument("src")
    ap.add_argument("dst", nargs="?")
    ap.add_argument("--from", dest="template",
                    help="encode: source container to copy checksum/prefix from")
    a = ap.parse_args()

    if a.mode in ("decode", "dump"):
        payload, checksum, prefix = decode(open(a.src, "rb").read())
        if a.mode == "dump":
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            print(f"# {os.path.basename(a.src)}: payload {len(payload)} bytes, "
                  f"checksum {checksum.decode('ascii', 'replace')}, "
                  f"prefix {prefix.hex() or '(none)'}")
            print(_pretty(payload))
        else:
            if not a.dst:
                ap.error("decode needs a destination path")
            open(a.dst, "wb").write(payload)
            print(f"{a.src} -> {a.dst} ({len(payload)} bytes)")
    else:
        if not (a.dst and a.template):
            ap.error("encode needs a destination and --from <original container>")
        _, checksum, prefix = decode(open(a.template, "rb").read())
        open(a.dst, "wb").write(encode(open(a.src, "rb").read(), checksum, prefix))
        print(f"{a.src} -> {a.dst} (checksum/prefix copied from {a.template})")


if __name__ == "__main__":
    main()
