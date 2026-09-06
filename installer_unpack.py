#!/usr/bin/env python3
r"""installer_unpack.py -- pull firmware and script payloads out of a Thermo
instrument installer without installing it.

Carves the cabinets out of a WiX Burn setup, reads the Burn manifest, extracts
the payload MSIs it names, and copies matching members out of the cabinets
stored inside them. A plain .msi may be given instead. Nothing is installed and
no vendor code runs.

Usage:
    python installer_unpack.py list    SETUP WORK_DIR
    python installer_unpack.py extract SETUP WORK_DIR OUT_DIR [--pattern GLOB ...]

Patterns match the MSI file identifier or the long file name, case-insensitively.
The defaults cover instrument firmware, FPGA bitstreams, ICL script libraries and
the TNGA host DLL. Carved cabinets are left in WORK_DIR (roughly the size of the
installer); delete it when done.

Windows only: needs expand.exe, olefile, and msilib (Python 3.12 or older).
"""

import argparse
import collections
import fnmatch
import hashlib
import json
import mmap
from pathlib import Path
import re
import shutil
import struct
import subprocess
import xml.etree.ElementTree as ET

import msilib
import olefile

EXPAND = r"C:\Windows\System32\expand.exe"
DEFAULT = ("*ftboot?", "*bzImage*", "*tng_firmware", "*.rbf", "*u-boot*.img",
           "*.lub", "*.xmb", "*.jsob", "*TNGEnc*.dll")


def sha(path, algorithm="sha256"):
    h = hashlib.new(algorithm)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def expand(cab, member, destination):
    destination.mkdir(parents=True, exist_ok=True)
    subprocess.run([EXPAND, "-F:" + member, str(cab), str(destination)],
                   check=True, capture_output=True)


def carve_cabs(source, work):
    """Write every embedded cabinet to work/. Returns (size, path), smallest first."""
    found = []
    with source.open("rb") as f, mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ) as data:
        for i, hit in enumerate(re.finditer(b"MSCF", data)):
            start = hit.start()
            size = struct.unpack("<I", data[start + 8:start + 12])[0]
            if size < 32 or start + size > len(data):
                continue
            cab = work / f"carve_{i}.cab"
            if not cab.exists() or cab.stat().st_size != size:
                cab.write_bytes(data[start:start + size])
            found.append((size, cab))
    return sorted(found)


def burn_payloads(cabs, work):
    """MSI payload entries from the Burn manifest in the smallest (UX) cabinet."""
    ux = work / "ux"
    expand(cabs[0][1], "*", ux)
    if not (ux / "0").exists():
        return []
    return [n.attrib for n in ET.parse(ux / "0").getroot().iter()
            if n.tag.endswith("Payload") and n.attrib.get("FilePath", "").lower().endswith(".msi")]


def fetch_msi(payload, cabs, work):
    """Extract one payload MSI, preferring a copy whose SHA-1 matches the manifest."""
    member = payload["SourcePath"]
    fallback = None
    for _, cab in cabs:
        destination = work / (Path(member).name + "_payload")
        try:
            expand(cab, member, destination)
        except subprocess.CalledProcessError:
            continue
        found = destination / member
        if not found.is_file():
            continue
        if "Hash" not in payload or sha(found, "sha1").upper() == payload["Hash"].upper():
            return found, True
        fallback = found
    return fallback, False


def msi_query(msi, sql, columns):
    db = msilib.OpenDatabase(str(msi), msilib.MSIDBOPEN_READONLY)
    view = db.OpenView(sql)
    view.Execute(None)
    rows = []
    while (row := view.Fetch()) is not None:
        rows.append(tuple(row.GetInteger(i) if kind is int else row.GetString(i)
                          for i, kind in enumerate(columns, 1)))
    return rows


def msi_files(msi):
    """(identifier, long name, size) for every file the package would install."""
    return [(i, n.split("|")[-1], s) for i, n, s in
            msi_query(msi, "SELECT File,FileName,FileSize FROM File", (str, str, int))]


def select(rows, patterns):
    """Map identifier -> (output name, size) for members matching any pattern."""
    repeated = {n for n, c in collections.Counter(n for _, n, _ in rows).items() if c > 1}
    wanted = {}
    for identifier, name, size in rows:
        if not any(fnmatch.fnmatch(identifier.lower(), p.lower())
                   or fnmatch.fnmatch(name.lower(), p.lower()) for p in patterns):
            continue
        # Long names repeat across script groups; the identifier is unique per package.
        out = identifier if name in repeated else name
        if Path(out).name != out or any(c in out for c in "/\\:"):
            raise ValueError("unsafe member name: " + out)
        wanted[identifier] = (out, size)
    return wanted


def msi_extract(msi, wanted, work, output):
    """Copy wanted members out of the cabinets stored inside the MSI."""
    written = []
    with olefile.OleFileIO(str(msi)) as compound:
        for index, name in enumerate(compound.listdir()):
            with compound.openstream(name) as stream:
                if stream.read(4) != b"MSCF":
                    continue
                stream.seek(0)
                cab = work / f"{msi.stem}_{index}.cab"
                with cab.open("wb") as dst:
                    shutil.copyfileobj(stream, dst)
            staged = work / f"{msi.stem}_{index}_files"
            if len(wanted) > 32:
                expand(cab, "*", staged)
            else:
                for member in wanted:
                    try:
                        expand(cab, member, staged)
                    except subprocess.CalledProcessError:
                        continue
            for member, (out, size) in wanted.items():
                source = staged / member
                if not source.is_file() or source.stat().st_size != size:
                    continue
                target = output / out
                if target.exists():
                    raise ValueError("duplicate output: " + out)
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(source, target)
                written.append({"member": member, "output": out, "bytes": size,
                                "sha256": sha(target)})
    return written


def packages(installer, work):
    """(label, path, hash verified) for every MSI to look inside."""
    if installer.suffix.lower() == ".msi":
        return [(installer.name, installer, True)]
    cabs = carve_cabs(installer, work)
    print(f"{installer.name}: {len(cabs)} cabinets carved")
    found = []
    for payload in burn_payloads(cabs, work):
        msi, verified = fetch_msi(payload, cabs, work)
        if msi is None:
            print(f"  {payload['FilePath']}: payload not found in any cabinet")
            continue
        found.append((payload["FilePath"], msi, verified))
    return found


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["list", "extract"])
    ap.add_argument("installer", type=Path, help="Burn setup .exe, or a plain .msi")
    ap.add_argument("work", type=Path, help="Scratch directory for carved cabinets")
    ap.add_argument("output", nargs="?", type=Path, help="New directory (extract only)")
    ap.add_argument("--pattern", nargs="+", default=list(DEFAULT))
    a = ap.parse_args()
    if a.mode == "extract" and not a.output:
        ap.error("extract needs an output directory")
    a.work.mkdir(parents=True, exist_ok=True)
    if a.output:
        a.output.mkdir(parents=True, exist_ok=False)

    report = {"installer": a.installer.name, "installer_sha256": sha(a.installer),
              "patterns": a.pattern, "packages": []}
    for label, msi, verified in packages(a.installer, a.work):
        properties = dict(msi_query(msi, "SELECT Property,Value FROM Property", (str, str)))
        rows = msi_files(msi)
        wanted = select(rows, a.pattern)
        print(f"  {label}: {properties.get('ProductName')} {properties.get('ProductVersion')} "
              f"| {len(rows)} files | {len(wanted)} matching"
              f"{'' if verified else ' | manifest hash NOT matched'}")
        entry = {"payload": label, "msi_sha256": sha(msi), "manifest_hash_verified": verified,
                 "product": properties.get("ProductName"),
                 "version": properties.get("ProductVersion"), "files": len(rows)}
        if a.mode == "list":
            for identifier, (out, size) in sorted(wanted.items(), key=lambda kv: kv[1][0]):
                print(f"    {out:<44} {size:>12,}  ({identifier})")
            entry["matching"] = [{"member": i, "name": o, "bytes": s}
                                 for i, (o, s) in sorted(wanted.items())]
        else:
            destination = a.output / Path(label).stem
            written = msi_extract(msi, wanted, a.work, destination)
            missing = sorted(set(wanted) - {w["member"] for w in written})
            print(f"    wrote {len(written)} files to {destination}"
                  + (f"; {len(missing)} not found in cabinets" if missing else ""))
            entry["extracted"] = written
            entry["missing"] = missing
        report["packages"].append(entry)

    target = (a.output or a.work) / f"{a.mode}.json"
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"report: {target}")


if __name__ == "__main__":
    main()
