#Thermo Mass spec analysis tools

utilities to extract readable firmware and scripts from your instrument. Will exctract code out of method files, ITCL files (.ICB stored in C:\Thermo\Instruments\), and thermo boot files (C:\Xcalibur\system\[INSTRUMENT TYPE]\instrument, these are XOR mapped tar.gz partitions streamed to the instrument every boot up)

This is very helpful for creating interoperable software to run instruments as allowed by §1201(f) since you can see the actual scripts and python running on the instrument.

Don't run this on your instrument workstation obviously, transfer the files you are interested in off first.

#what each script does

| Script | Does |
|---|---|
| `icb_codec.py` | Decode/encode ITCL `.ICB` files (XOR 0x01 on even offsets). `decode in out` / `encode in out`. Discovered in SI of 10.1021/acs.analchem.6b03390,|
| `msx_codec.py` | Decode/encode Exactive `.mstune`/`.mscal`/`.cfg`/`procedure_history` (XOR 0x51 → ZIP). `decode`/`dump`/`encode`. |
| `ftboot_unpack.py` | Decode + gzip-validate the four `ftboot*` firmware images (position mask → gzip → tar/kernel). `ftboot_unpack.py SRC_DIR OUT_DIR`. extracts the firmware that runs on instrument|
| `run_full_extraction.sh` | One-shot driver: runs `ftboot_unpack.py`, extracts the tars, decompiles ftboot3 `pyinst/*.pyc`, writes inventories/manifest. `SRC OUT LABEL`. runs entire workflow|

#Dependencies

uncompyle6
