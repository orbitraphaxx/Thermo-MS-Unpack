# Thermo Mass spec analysis tools

utilities to extract readable firmware, scripts and configuration from your instrument. Will extract code out of method files, ITCL files (Ion Trap Control Language, .ICB stored in C:\Thermo\Instruments\), thermo boot files (C:\Xcalibur\system\[INSTRUMENT TYPE]\instrument, these are XOR masked tar.gz partitions streamed to the instrument every boot up), and the newer TNGA files (.lub Lua control scripts, .xmb/.jsob device/tune/cal configs) used on Astral, Exploris, Tribrid, Stellar and TSQ Series II. There is also a tool to pull any of those out of an installer you already have, without installing it.

The purpose is interoperability: reading the scripts, python and lua the instrument actually runs so you can write independent software that talks to it. §1201(f) permits both the analysis and making the information and the means available to others, provided it's solely to enable interoperability of an independently created program and doesn't otherwise infringe.

Use these on software your lab is licensed to run. Every tool works on files you supply from your own installation, nothing is bundled here. No vendor code, firmware or key material is in this repo, the TNGA decoder reads the key and IV out of the copy of TNGEnc.dll that came with your own software. I am not uploading the files or results of these tools.

Don't run this on your instrument workstation obviously, transfer the files you are interested in off first.

# What each script does

| Script | Does |
|---|---|
| `icb_codec.py` | Decode/encode ITCL `.ICB` files (XOR 0x01 on even offsets). `decode in out` / `encode in out`. Discovered in SI of 10.1021/acs.analchem.6b03390. |
| `msx_codec.py` | Decode/encode Exactive `.mstune`/`.mscal`/`.cfg`/`procedure_history` (XOR 0x51 → ZIP). `decode`/`dump`/`encode`. |
| `ftboot_unpack.py` | Decode + gzip-validate the four `ftboot*` firmware images (position mask → gzip → tar/kernel). `ftboot_unpack.py SRC_DIR OUT_DIR`. extracts the firmware that runs on instrument |
| `run_full_extraction.sh` | One-shot driver: runs `ftboot_unpack.py`, extracts the tars, decompiles ftboot3 `pyinst/*.pyc`, writes inventories/manifest. `SRC OUT LABEL`. runs entire workflow |
| `tnga_decode.py` | Decode TNGA files (`.lub`/`.xmb`/`.jsob`, AES-256-CBC) to lua/xml/json. `tnga_decode.py TNGEnc.dll FILE_OR_DIR OUT_DIR`. `.lub` is the lua control layer, `.xmb`/`.jsob` the device, tune and calibration configuration |
| `installer_unpack.py` | Carve a WiX Burn setup, read its manifest, and copy firmware/script members out of the payload MSIs. `list SETUP WORK` / `extract SETUP WORK OUT [--pattern GLOB ...]`. for working from installation media rather than a live instrument |

# Typical workflow

Boot images (Exactive/QE, Exploris, Tribrid, Astral — anything shipping `ftboot0..3`):

    python installer_unpack.py extract Setup.exe work fw --pattern "*ftboot?"
    ./run_full_extraction.sh fw/OlympusMSI out astral

or point `run_full_extraction.sh` straight at the instrument directory you copied off the workstation. Every gzip member is CRC/size validated, so a wrong mask fails loudly rather than producing garbage.

TNGA lua + configs:

    python installer_unpack.py extract Setup.exe work tng
    python tnga_decode.py tng/ThoriumMSI/TNGEnc.dll tng/ICLLibrary lua

The default `--pattern` set already covers `.lub`, `.xmb`, `.jsob`, firmware, FPGA bitstreams and `TNGEnc.dll`, so plain `extract` usually gets everything you need. The decoder locates the key and IV in whichever `TNGEnc.dll` you hand it, then checks PKCS#7 padding and the declared plaintext length on every file; wrong constants can't silently produce junk. Output goes to `.lua`/`.xml`/`.json` with a `manifest.json` of input/output hashes.

ITCL and tune/cal files are single files, straight from the workstation:

    python icb_codec.py decode mxinit.ICB mxinit.itcl
    python msx_codec.py dump master_cal.mscal

# Notes

- `installer_unpack.py` writes carved cabinets into `WORK`; budget about the size of the installer and delete it afterwards. `list` prints the product, version and matching members without writing any of them out.
- MSI long file names repeat (several copies of `TNGEnc.dll`, per-instrument config variants, script groups), so anything ambiguous is written under its unique MSI file identifier — `SC_TNGEnc.dll`, `SC_TNGEnc.dll_1` and so on. Any copy of the DLL works. The report json records identifier and name for everything it wrote.
- Stellar and TSQ Series II don't use `ftboot` — they ship `bzImage.tng-intel` + `tng_firmware` as ordinary files in the MSI, so `installer_unpack.py` is all you need for those; the interesting layer there is the `.lub` library.
- `ftboot_unpack.py` expects the images named `ftboot0`..`ftboot3` in one directory, which is how they install.
- `icb_codec.py encode` round-trips byte for byte. `msx_codec.py encode` rebuilds the ZIP container and copies the checksum from the original (its derivation is unknown), so the file is not byte-identical and has not been tested against a live instrument's validation. Back up first.

# Dependencies

    pip install uncompyle6 pefile pycryptodome olefile

`uncompyle6` for the ftboot3 python, `pefile`+`pycryptodome` for `tnga_decode.py`, `olefile` for `installer_unpack.py`. The installer tool is Windows only (uses `expand.exe` and `msilib`, so Python 3.12 or older). `icb_codec.py`, `msx_codec.py` and `ftboot_unpack.py` are standard library only.
