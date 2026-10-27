#!/usr/bin/env python3
"""Execute complete read-only witness collection with synthetic ELF and 101-symbol manifest.

The earlier CI only py_compiled the source and exercised imports(...), missing
a runtime UnboundLocalError when report was mutated before assignment.
"""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
WITNESS=REPO/"scripts/nevada-ar9271-live-core-kmi-witness.py"
MANIFEST=REPO/"ci/nevada-ar9271-core-kmi.tsv"

def synthetic_elf():
    shstr=b"\0.shstrtab\0__versions\0"
    record=struct.pack("<Q",0x61a2317d)+b"usb_submit_urb\0".ljust(56,b"\0")
    obj=bytearray(512)
    obj[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    shoff=320
    struct.pack_into("<HHIQQQIHHHHHH",obj,16,1,183,1,0,0,shoff,0,64,0,0,64,3,1)
    obj[64:64+len(shstr)]=shstr
    obj[112:176]=record
    header="<IIQQQQIIQQ"
    struct.pack_into(header,obj,shoff+64,1,3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(header,obj,shoff+128,11,1,0,0,112,64,0,0,8,64)
    return bytes(obj)

with tempfile.TemporaryDirectory(prefix="nevada-witness-selftest-") as temp:
    root=Path(temp)
    modules=root/"stock-modules"
    modules.mkdir()
    (modules/"example.ko").write_bytes(synthetic_elf())
    report=root/"report.json"
    result=subprocess.run([
        sys.executable,str(WITNESS),"--manifest",str(MANIFEST),
        "--offline-dir",str(modules),"--output",str(report)],
        check=False,capture_output=True,text=True,timeout=20
    )
    print(result.stdout)
    if result.returncode:
        raise SystemExit("Witness end-to-end offline test failed:\n"+result.stderr)
    data=json.loads(report.read_text())
    assert data["mode"]=="offline_recovery_fixture"
    assert data["matching_symbol_witnesses"]==1
    assert data["matching_import_witness_entries"]==1
    assert data["conflicting_symbol_witnesses"]==0
    assert data["required_unique_core_symbols"]==101
    assert data["module_ELFs_read"]==1
    assert data["core_export_name_visibility"]=={
        "rfkill_pause_polling":"unavailable",
        "usb_get_urb":"unavailable",
        "kallsyms_exports_visible":False
    },data["core_export_name_visibility"]
    print("PASS: end-to-end report creation, runtime field initialization and import CRC classification")
