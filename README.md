#Thermo Mass spec analysis tools

utilities to extract readable firmware, scripts and configuration from your instrument. Will extract code out of method files, ITCL files (.ICB stored in C:\\Thermo\\Instruments), thermo boot files (C:\\Xcalibur\\system\[INSTRUMENT TYPE]\\instrument, these are XOR masked tar.gz partitions streamed to the instrument every boot up), and the newer TNGA files (.lub Lua control scripts, .xmb/.jsob device/tune/cal configs) used on Astral, Exploris, Tribrid, Stellar and TSQ Series II. There is also a tool to pull any of those out of an installer you already have, without installing it.

This is very helpful for creating interoperable software to run instruments as allowed by §1201(f) since you can see the actual scripts, python and lua running on the instrument.

Don't run this on your instrument workstation obviously, transfer the files you are interested in off first. I am not uploading the files or results of these tools. No vendor code, firmware or key material is in this repo, the TNGA decoder reads the key and IV out of the copy of TNGEnc.dll that came with your own software. §1201(f) permits making both the information and the circumvention means available to others, provided it's solely to enable interoperability of an independently created program and doesn't otherwise infringe.

\#what each script does

|Script|Does|
|-|-|
|`icb\_codec.py`|Decode/encode ITCL `.ICB` files (XOR 0x01 on even offsets). `decode in out` / `encode in out`. Discovered in SI of 10.1021/acs.analchem.6b03390.|
|`msx\_codec.py`|Decode/encode Exactive `.mstune`/`.mscal`/`.cfg`/`procedure\_history` (XOR 0x51 → ZIP). `decode`/`dump`/`encode`.|
|`ftboot\_unpack.py`|Decode + gzip-validate the four `ftboot\*` firmware images (position mask → gzip → tar/kernel). `ftboot\_unpack.py SRC\_DIR OUT\_DIR`. extracts the firmware that runs on instrument|
|`run\_full\_extraction.sh`|One-shot driver: runs `ftboot\_unpack.py`, extracts the tars, decompiles ftboot3 `pyinst/\*.pyc`, writes inventories/manifest. `SRC OUT LABEL`. runs entire workflow|
|`tnga\_decode.py`|Decode TNGA files (`.lub`/`.xmb`/`.jsob`, AES-256-CBC) to lua/xml/json. `tnga\_decode.py TNGEnc.dll FILE\_OR\_DIR OUT\_DIR`. gets you the lua instrument control library and the device/tune/cal configs|
|`installer\_unpack.py`|Carve a WiX Burn setup, read its manifest, and copy firmware/script members out of the payload MSIs. `list SETUP WORK` / `extract SETUP WORK OUT \[--pattern GLOB ...]`. how you get the files above off an installer instead of a live instrument|

\#typical workflow

Boot images (Exactive/QE, Exploris, Tribrid, Astral — anything shipping `ftboot0..3`):

&#x20;   python installer\_unpack.py extract Setup.exe work fw --pattern "\*ftboot?"
    ./run\_full\_extraction.sh fw/OlympusMSI out astral


or point `run\_full\_extraction.sh` straight at the instrument directory you copied off the workstation. Every gzip member is CRC/size validated, so a wrong mask fails loudly rather than producing garbage.

TNGA lua + configs:

&#x20;   python installer\_unpack.py extract Setup.exe work tng
    python tnga\_decode.py tng/ThoriumMSI/TNGEnc.dll tng/ICLLibrary lua


The default `--pattern` set already covers `.lub`, `.xmb`, `.jsob`, firmware, FPGA bitstreams and `TNGEnc.dll`, so plain `extract` usually gets everything you need. The decoder locates the key and IV in whichever `TNGEnc.dll` you hand it, then checks PKCS#7 padding and the declared plaintext length on every file; wrong constants can't silently produce junk. Output goes to `.lua`/`.xml`/`.json` with a `manifest.json` of input/output hashes.

ITCL and tune/cal files are single files, straight from the workstation:

&#x20;   python icb\_codec.py decode mxinit.ICB mxinit.itcl
    python msx\_codec.py dump master\_cal.mscal


\#notes

* `installer\_unpack.py` writes carved cabinets into `WORK`; budget about the size of the installer and delete it afterwards. `list` prints the product, version and matching members without writing any of them out.
* MSI long file names repeat (several copies of `TNGEnc.dll`, per-instrument config variants, script groups), so anything ambiguous is written under its unique MSI file identifier — `SC\_TNGEnc.dll`, `SC\_TNGEnc.dll\_1` and so on. Any copy of the DLL works. The report json records identifier and name for everything it wrote.
* Stellar and TSQ Series II don't use `ftboot` — they ship `bzImage.tng-intel` + `tng\_firmware` as ordinary files in the MSI, so `installer\_unpack.py` is all you need for those; the interesting layer there is the `.lub` library.
* `ftboot\_unpack.py` expects the images named `ftboot0`..`ftboot3` in one directory, which is how they install.
* `icb\_codec.py encode` round-trips byte for byte. `msx\_codec.py encode` rebuilds the ZIP container and copies the checksum from the original (its derivation is unknown), so the file is not byte-identical and has not been tested against a live instrument's validation. Back up first.

\#Dependencies

&#x20;   pip install uncompyle6 pefile pycryptodome olefile


`uncompyle6` for the ftboot3 python, `pefile`+`pycryptodome` for `tnga\_decode.py`, `olefile` for `installer\_unpack.py`. The installer tool is Windows only (uses `expand.exe` and `msilib`, so Python 3.12 or older). `icb\_codec.py`, `msx\_codec.py` and `ftboot\_unpack.py` are standard library only.

