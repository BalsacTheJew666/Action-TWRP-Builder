#!/usr/bin/env python3
"""Synthetic ELF64 end-to-end provider-name attribution test. No device or su."""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SCRIPT=ROOT/"scripts/nevada-vendor-module-export-attribution.py"
STOCK=ROOT/"scripts/nevada-stock-vendor-kmi-import-inventory.py"

def module_elf(export_names):
    shstr=b"\0.shstrtab\0__ksymtab_strings\0"
    strings=b"".join(x.encode()+b"\0" for x in export_names)
    data=bytearray(1024)
    data[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    section_offset=640
    struct.pack_into("<HHIQQQIHHHHHH",data,16,1,183,1,0,0,
                     section_offset,0,64,0,0,64,3,1)
    data[64:64+len(shstr)]=shstr
    data[192:192+len(strings)]=strings
    fmt="<IIQQQQIIQQ"
    struct.pack_into(fmt,data,section_offset+64,1,3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(fmt,data,section_offset+128,
                     shstr.index(b"__ksymtab_strings"),1,0,0,192,len(strings),0,0,1,0)
    return bytes(data)

with tempfile.TemporaryDirectory(prefix="nevada-export-provider-selftest-") as d:
    folder=Path(d)
    modules=folder/"modules"
    modules.mkdir()
    (modules/"mtk_provider.ko").write_bytes(module_elf(
        ["vendor_internal_sharemem","rfkill_pause_polling"]))
    (modules/"wifi_provider.ko").write_bytes(module_elf(["vendor_internal_sharemem"]))
    meta=folder/"stock-private-import-metadata.json"
    meta.write_text(json.dumps({
      "mode":"offline_test_fixture",
      "public_gki_core_export_count":2,
      "symbol_records":[
        {"symbol":"vendor_internal_sharemem","imported_versions":[
          {"import_crc":"0x11111111","category":"not_in_public_gki"}]},
        {"symbol":"unresolved_vendor_symbol","imported_versions":[
          {"import_crc":"0x22222222","category":"not_in_public_gki"}]},
        {"symbol":"module_layout","imported_versions":[
          {"import_crc":"0x33333333","category":"public_gki_crc_match"}]},
      ]
    }))
    output=folder/"provider-report.json"
    cmd=[sys.executable,str(SCRIPT),
       "--stock-import-report",str(meta),
       "--stock-inventory-script",str(STOCK),
       "--offline-dir",str(modules),
       "--output",str(output)]
    r=subprocess.run(cmd,capture_output=True,text=True,timeout=20)
    print(r.stdout)
    if r.returncode:
        raise SystemExit("Failed offline provider audit: "+r.stderr)
    d=json.loads(output.read_text())
    assert d["source_stock_inventory_name_count"]==2
    assert d["unique_module_elfs_parsed"]==2
    assert d["possible_provider_export_name_found_in_loaded_stock_module_ELF"]==1
    assert d["multiple_possible_module_exporters"]==1
    assert d["non_public_import_name_unresolved"]==1
    assert d["not_yet_attributed_symbol_names"]==["unresolved_vendor_symbol"]
    assert d["possible_module_export_providers"]["vendor_internal_sharemem"]==["mtk_provider","wifi_provider"]
    assert d["two_AR9271_known_gki_missing_exports"]["rfkill_pause_polling"]["name_seen_in_stock_module_export_section"] is False
    # rfkill_pause_polling was not a missing import in this fixture; if
    # no one imports it, the provider-name result appropriately excludes it.
    assert output.stat().st_mode & 0o777==0o600
    print("PASS: two possible module exporters, one truly unresolved import; no device use")
