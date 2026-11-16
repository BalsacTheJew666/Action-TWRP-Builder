#!/usr/bin/env python3
"""Full no-device regression test of the private vendor export provider CLI."""
from pathlib import Path
import importlib.util
import json
import os
import struct
import subprocess
import sys
import tempfile
from unittest import mock

REPO=Path(__file__).resolve().parents[1]
SCRIPT=REPO/"scripts/nevada-vendor-export-provider-local.py"
WITNESS=REPO/"scripts/nevada-ar9271-live-core-kmi-witness.py"
OFFICIAL_SHA="bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0"

def fake_module(name,crc):
    shstr=b"\0.shstrtab\0.strtab\0.symtab\0__ksymtab_strings\0"
    strtab=b"\0__ksymtab_"+name.encode()+b"\0__crc_"+name.encode()+b"\0"
    index_crc=strtab.index(b"__crc_")
    indices={k:shstr.index(k.encode()) for k in (".shstrtab",".strtab",".symtab","__ksymtab_strings")}
    binary=bytearray(2048)
    binary[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    shoff=1024
    struct.pack_into("<HHIQQQIHHHHHH",binary,16,
                     1,183,1,0,0,shoff,0,64,0,0,64,5,1)
    binary[64:64+len(shstr)]=shstr
    binary[192:192+len(strtab)]=strtab
    # Entry 0 all zero. Defined __ksymtab_ symbol points at section 4;
    # __crc_ is the ABS 32-bit CRC that the exporter records.
    struct.pack_into("<IBBHQQ",binary,512+24,
                     1,0x10,0,4,0,0)
    struct.pack_into("<IBBHQQ",binary,512+48,
                     index_crc,0x10,0,0xfff1,crc,0)
    strings=name.encode()+b"\0"
    binary[384:384+len(strings)]=strings
    fmt="<IIQQQQIIQQ"
    struct.pack_into(fmt,binary,shoff+64,indices[".shstrtab"],3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(fmt,binary,shoff+128,indices[".strtab"],3,0,0,192,len(strtab),0,0,1,0)
    struct.pack_into(fmt,binary,shoff+192,indices[".symtab"],2,0,0,512,72,2,0,8,24)
    struct.pack_into(fmt,binary,shoff+256,indices["__ksymtab_strings"],1,0,0,384,len(strings),0,0,1,0)
    return bytes(binary)

spec=importlib.util.spec_from_file_location("providers",SCRIPT)
app=importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)
name="vendor_module_export_test"
crc=0x12345678
raw=fake_module(name,crc)
exports,crcs,weak,has_symtab=app.exports_from_elf(raw,{name,"other"})
assert has_symtab and exports=={name:"defined_ksymtab_symbol"},exports
assert crcs=={name:crc},crcs
assert not weak,weak
print("PASS: synthetic ELF64 defined __ksymtab_ provider and __crc_ ABS extraction")

with tempfile.TemporaryDirectory(prefix="nevada-vendor-provider-CI-") as directory:
    root=Path(directory)
    mods=root/"modules"
    mods.mkdir()
    (mods/"example.ko").write_bytes(raw)
    original={
      "mode":"offline_CI_synthetic",
      "official_gki_reference_sha256":OFFICIAL_SHA,
      "symbol_inventory":{
        name:{
          "bucket":"not_an_official_public_gki_vmlinux_export",
          "distinct_import_crcs":[f"0x{crc:08x}"],
        },
        "vendor_absent":{
          "bucket":"not_an_official_public_gki_vmlinux_export",
          "distinct_import_crcs":["0xcafebabe"],
        },
        "usb_get_urb":{
          "bucket":"not_an_official_public_gki_vmlinux_export",
          "distinct_import_crcs":["0x3c85197c"],
        },
      },
      "names_not_in_8473_public_plus_two_candidate":[name,"vendor_absent"],
    }
    original_file=root/"original-private-inventory.json"
    original_file.write_text(json.dumps(original))
    report=root/"classified.json"
    invocation=[
      sys.executable,str(SCRIPT),
      "--inventory-json",str(original_file),
      "--witness-script",str(WITNESS),
      "--report",str(report),
      "--offline-dir",str(mods)
    ]
    completed=subprocess.run(invocation,capture_output=True,text=True,timeout=30)
    print(completed.stdout)
    if completed.returncode:
        raise SystemExit(completed.stderr+" exit: "+str(completed.returncode))
    findings=json.loads(report.read_text())
    assert findings["mode"]=="offline_CI_synthetic"
    assert findings["module_ELFs_examined"]==1
    assert findings["public_GKI_absent_imported_names_examined"]==2
    assert findings["result_buckets"]=={
        "one_loaded_module_ELF_declaration":1,
        "no_provider_seen_among_readable_loaded_modules":1,
    },findings["result_buckets"]
    assert findings["export_crc_comparison"]["available_export_crc_comparisons_matching"]==1
    assert findings["export_crc_comparison"]["available_export_crc_comparisons_conflicting"]==0
    assert findings["provider_candidates"][name]["loaded_module_ELF_export_declarations"]==["example"]
    assert findings["provider_candidates"]["vendor_absent"]["classification"]=="no_provider_seen_among_readable_loaded_modules"
    assert "usb_get_urb" not in findings["provider_candidates"]
    assert (report.stat().st_mode&0o777)==0o600
    assert json.loads(original_file.read_text())==original
    print("PASS: end-to-end provider classification, no device/root, local 0600 JSON")

    # Collision warning: an ELF export CRC different from the importing module
    # must not be silently called a match or a core-kernel export.
    wrong={name:{"example":crc^1}}
    _,_,counts=app.classify_inventory(original,wrong,{}, {})
    assert counts["available_export_crc_comparisons_conflicting"]==1
    print("PASS: negative CRC mismatch classification")
