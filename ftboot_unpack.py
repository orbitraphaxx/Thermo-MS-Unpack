#!/usr/bin/env python3
"""Decode Thermo Exactive ftboot images offline, preserving the source files.

Usage (from any directory):
  python ftboot_unpack.py SOURCE_DIRECTORY NEW_OUTPUT_DIRECTORY

"""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import tarfile
import zlib

PERIOD = 0x2000000
CACHE_PERIOD = 0x80000
CHUNK = 1024 * 1024


def mask_byte(i):
    value = (0x51, 0x50, 0x7f, 0x51)[i % 4]
    if i % 2 == 0:
        value ^= i & 0xfc
        for selector, constant in ((0x30, 0xa2), (0x1000200, 0x38), (0x400, 0x05),
                                   (0x1000, 0x20), (0x8000, 0x1b), (0x40000, 0x7e)):
            if i & selector:
                value ^= constant
    return value


# Low address bits repeat every512KiB within each16MiB half of the full period.
# CHUNK divides16MiB, so a read never crosses between those two mask variants.
MASK_LOW = bytes(map(mask_byte, range(CACHE_PERIOD))) * 2
MASK_HIGH = bytes(mask_byte(i | 0x1000000) for i in range(CACHE_PERIOD)) * 2


def decode_file(source, target):
    source_hash, target_hash = hashlib.sha256(), hashlib.sha256()
    size = 0
    with source.open('rb') as src, target.open('xb') as dst:
        while data := src.read(CHUNK):
            mask = MASK_HIGH if size & 0x1000000 else MASK_LOW
            decoded = bytes(a ^ b for a, b in zip(data, mask))
            dst.write(decoded)
            source_hash.update(data)
            target_hash.update(decoded)
            size += len(data)
    return {'source': str(source.resolve()), 'source_bytes': size,
            'source_sha256': source_hash.hexdigest(), 'decoded_file': target.name,
            'decoded_sha256': target_hash.hexdigest()}


def inflate_member(source, offset, target):
    state = zlib.decompressobj(31)
    digest = hashlib.sha256()
    size, crc, consumed = 0, 0, 0
    with source.open('rb') as src, target.open('xb') as dst:
        src.seek(offset)
        while not state.eof:
            data = src.read(CHUNK)
            if not data:
                raise ValueError(f'{source}: incomplete gzip stream at {offset:#x}')
            consumed += len(data)
            pending = data
            while pending and not state.eof:
                out = state.decompress(pending, CHUNK)
                pending = state.unconsumed_tail
                dst.write(out)
                digest.update(out)
                size += len(out)
                crc = zlib.crc32(out, crc)
        consumed -= len(state.unused_data)
        end = offset + consumed
        src.seek(end - 8)
        stored_crc, stored_size = struct.unpack('<II', src.read(8))
    if (crc & 0xffffffff, size & 0xffffffff) != (stored_crc, stored_size):
        raise ValueError('gzip trailer disagrees with independently calculated CRC/size')
    return {'gzip_offset': offset, 'gzip_end': end, 'gzip_bytes': consumed,
            'gzip_crc32': f'{stored_crc:08x}', 'gzip_isize': stored_size,
            'gzip_validated': True, 'payload_file': target.name, 'payload_bytes': size,
            'payload_sha256': digest.hexdigest(),
            'trailing_bytes': source.stat().st_size - end}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('source', type=Path)
    ap.add_argument('output', type=Path, help='New directory (must not already exist)')
    ap.add_argument('--files', nargs='+', type=int, choices=range(4), default=list(range(4)),
                    help='Image numbers to decode (default:0 1 2 3)')
    args = ap.parse_args()
    numbers = list(dict.fromkeys(args.files))
    sources = [args.source / f'ftboot{i}' for i in numbers]
    for source in sources:
        if not source.is_file():
            ap.error(f'Missing input: {source}')
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'mask_period': PERIOD, 'files': []}
    for i, source in zip(numbers, sources):
        decoded = args.output / (f'ftboot{i}.bzImage' if i == 0 else f'ftboot{i}.tar.gz')
        entry = decode_file(source, decoded)
        with decoded.open('rb') as f:
            head = f.read(65536) if i == 0 else b''
        if i == 0:
            if head[0x202:0x206] != b'HdrS' or head[0x1fe:0x200] != b'\x55\xaa':
                raise ValueError('Decoded ftboot0 lacks Linux x86 boot signatures')
            offset = head.find(b'\x1f\x8b\x08')
            if offset < 0:
                raise ValueError('No embedded kernel gzip header in first 64 KiB')
            payload = args.output / 'ftboot0.kernel.elf'
        else:
            offset = 0
            payload = args.output / f'ftboot{i}.tar'
        entry.update(inflate_member(decoded, offset, payload))
        if i == 0:
            with payload.open('rb') as f:
                if f.read(4) != b'\x7fELF':
                    raise ValueError('Inflated kernel is not ELF')
        else:
            if entry['trailing_bytes']:
                raise ValueError('Unexpected data after archive gzip member')
            with tarfile.open(payload, 'r:') as archive:
                members = archive.getmembers()
                inventory = [{'name': m.name, 'size': m.size,
                              'type': m.type.decode('ascii', 'backslashreplace'),
                              'linkname': m.linkname, 'mode': oct(m.mode),
                              'uid': m.uid, 'gid': m.gid, 'mtime': m.mtime}
                             for m in members]
            inventory_path = args.output / f'ftboot{i}.inventory.json'
            inventory_path.write_text(json.dumps(inventory, indent=2), encoding='utf-8')
            entry['tar_members'] = len(members)
            entry['tar_regular_files'] = sum(m.isfile() for m in members)
            entry['tar_regular_bytes'] = sum(m.size for m in members if m.isfile())
            entry['inventory_file'] = inventory_path.name
        report['files'].append(entry)
        (args.output / 'manifest.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
        print(json.dumps(entry), flush=True)


if __name__ == '__main__':
    main()
