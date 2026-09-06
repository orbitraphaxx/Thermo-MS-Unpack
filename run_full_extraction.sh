#!/usr/bin/env bash
# Full, clean firmware extraction for one ftboot source set.
# Usage: run_full_extraction.sh <source_dir_with_ftboot0..3> <output_dir> <label>
# Produces, under <output_dir>:
#   ftboot0.kernel.elf        decompressed Linux kernel (validated)
#   ftboot1_fs/ 2_fs/ 3_fs/   extracted tar trees
#   ftboot3_src/              ftboot3 pyinst/*.pyc decompiled to .py
#   inventories/, manifest.json
# Intermediate .tar/.tar.gz are removed after extraction (regenerable from source).
set -e
SRC="$1"; OUT="$2"; LABEL="$3"
TOOLS="$(cd "$(dirname "$0")" && pwd)"
DEC="$OUT/_decoded"
echo "### [$LABEL] decode+validate all four images"
python "$TOOLS/ftboot_unpack.py" "$SRC" "$DEC" >/dev/null
mkdir -p "$OUT/inventories"
cp "$DEC/ftboot0.kernel.elf" "$OUT/ftboot0.kernel.elf"
cp "$DEC/manifest.json" "$OUT/manifest.json"
cp "$DEC"/ftboot*.inventory.json "$OUT/inventories/" 2>/dev/null || true
for n in 1 2 3; do
  echo "### [$LABEL] extract ftboot${n}.tar -> ftboot${n}_fs/"
  mkdir -p "$OUT/ftboot${n}_fs"
  python - "$DEC/ftboot${n}.tar" "$OUT/ftboot${n}_fs" <<'PY'
import sys, tarfile
tar, dest = sys.argv[1], sys.argv[2]
with tarfile.open(tar) as t:
    for m in t.getmembers():
        if m.isfile() or m.isdir():
            t.extract(m, dest)
PY
done
echo "### [$LABEL] decompile ftboot3 pyinst -> ftboot3_src/"
python - "$OUT/ftboot3_fs" "$OUT/ftboot3_src" <<'PY'
import sys, os
from pathlib import Path
from uncompyle6.main import decompile_file
fs, dst = Path(sys.argv[1]), Path(sys.argv[2])
pyinst = next(fs.rglob("pyinst"), None)
if pyinst is None:
    print("  no pyinst dir found"); raise SystemExit
ok=fail=0; fails=[]
for pyc in sorted(pyinst.rglob("*.pyc")):
    rel = pyc.relative_to(pyinst).with_suffix(".py")
    outp = dst/rel; outp.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(outp,"w",encoding="utf-8") as f: decompile_file(str(pyc), f)
        ok+=1
    except Exception: fail+=1; fails.append(rel.as_posix())
print(f"  decompiled ok={ok} fail={fail} {fails}")
PY
echo "### [$LABEL] removing intermediates (_decoded)"
rm -rf "$DEC"
echo "### [$LABEL] DONE"
