#!/usr/bin/env python3
"""End-to-end test read-only vendor import inventory with synthetic module only.

CI passes actual public GKI 14563692 symvers but never touches device/vendor
ELFs or runs su. Ensures importer classification and local report creation.
"""
import json
import pathlib
import struct
import subprocess
import sys
import tempfile

REPO=pathlib.Path(__file__).resolve().parents[1]
PROGRAM=REPO/"scripts/nevada-vendor-core-abi-private-inventory.py"
WITNESS=REPO/"scripts/nevada-ar9271-live-core-kmi-witness.py"
CORE=REPO/"ci/nevada-ar9271-core-kmi.tsv"

def make_elf(entries):
    shstr=b"\0.shstrtab\0__versions\0"
    records=b"".join(
        struct.pack("<Q",crc)+ (symbol.encode()+b"\0").ljust(56,b"\0")
        for symbol,crc in entries
    )
    data=bytearray(2048)
    data[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    shoff=1408
    struct.pack_into("<HHIQQQIHHHHHH",data,16,
                     1,183,1,0,0,shoff,0,64,0,0,64,3,1)
    data[64:64+len(shstr)]=shstr
    data[128:128+len(records)]=records
    spec="<IIQQQQIIQQ"
    struct.pack_into(spec,data,shoff+64,1,3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(spec,data,shoff+128,11,1,0,0,128,len(records),0,0,8,64)
    return bytes(data)

if len(sys.argv)!=2:
    raise SystemExit("usage: selftest.py /path/to/official-vmlinux.symvers")
reference=pathlib.Path(sys.argv[1])
with tempfile.TemporaryDirectory(prefix="nevada-private-inventory-CI-") as folder:
    temp=pathlib.Path(folder)
    mods=temp/"modules"
    mods.mkdir()
    # Published GKI/required core CRC, conflict and non-public-module import.
    (mods/"synthetic.ko").write_bytes(make_elf([
        ("usb_submit_urb",0x61a2317d),
        ("module_layout",0x0222dd63 ^ 1),
        ("example_vendor_private_sym",0xdeadbeef),
    ]))
    report=temp/"report.json"
    r=subprocess.run(
      [sys.executable,str(PROGRAM),"--witness-script",str(WITNESS),
       "--official-gki-symvers",str(reference),
       "--core-import-manifest",str(CORE),
       "--offline-dir",str(mods),
       "--report",str(report)],
       capture_output=True,text=True,timeout=30
    )
    print(r.stdout)
    if r.returncode:
        raise SystemExit(r.stderr or f"Inventory exited {r.returncode}")
    result=json.loads(report.read_text())
    assert result["mode"]=="offline_CI_synthetic"
    assert result["already_loaded_module_elfs_examined"]==1
    assert result["distinct_imported_symbol_names"]==3
    assert result["core_101_symbol_witnesses_matching"]==1
    assert result["core_101_symbol_witnesses_conflicting"]==1
    assert result["core_101_symbol_witnesses_without_evidence"]==99
    assert result["names_not_in_8473_public_plus_two_candidate_count"]==1
    assert result["imported_symbol_buckets"]=={
        "matches_official_public_gki_crc":1,
        "differs_from_official_public_gki_crc":1,
        "not_an_official_public_gki_vmlinux_export":1
    },result["imported_symbol_buckets"]
    assert result["symbol_inventory"]["module_layout"]["bucket"]=="differs_from_official_public_gki_crc"
    assert result["symbol_inventory"]["example_vendor_private_sym"]["bucket"]=="not_an_official_public_gki_vmlinux_export"
    assert result["required_blockers"]["usb_get_urb"]["actual_live_export_proven"] is False
    print("PASS: complete offline import classification and private report generation; no root or kernel modification.")
