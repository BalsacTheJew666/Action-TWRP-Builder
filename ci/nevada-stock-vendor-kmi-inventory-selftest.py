#!/usr/bin/env python3
"""End-to-end synthetic test of the read-only Motorola stock module inventory.

No device access and no privileged operations. Uses Linux 5.15-like ELF64
__versions records; checks classification and differing/alias module handling.
"""
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile

HERE=Path(__file__).resolve().parents[1]
INVENTORY=HERE/"scripts/nevada-stock-vendor-kmi-import-inventory.py"

def synthetic_module(symbol,crc):
    shstr=b"\0.shstrtab\0__versions\0"
    entry=struct.pack("<Q",crc)+symbol.encode().ljust(56,b"\0")
    obj=bytearray(512)
    obj[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    shoff=320
    struct.pack_into("<HHIQQQIHHHHHH",obj,16,1,183,1,0,0,shoff,
                     0,64,0,0,64,3,1)
    obj[64:64+len(shstr)]=shstr
    obj[112:176]=entry
    header="<IIQQQQIIQQ"
    struct.pack_into(header,obj,shoff+64,1,3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(header,obj,shoff+128,11,1,0,0,112,64,0,0,8,64)
    return bytes(obj)

with tempfile.TemporaryDirectory(prefix="nevada-stock-kmi-") as tmp:
    d=Path(tmp)
    root=d/"modules"
    (root/"a").mkdir(parents=True)
    (root/"b").mkdir(parents=True)
    (root/"c").mkdir(parents=True)
    # Duplicate filename with identical bytes is safe to count just once.
    (root/"a"/"wifi-foo.ko").write_bytes(synthetic_module(
        "usb_submit_urb",0x61a2317d))
    (root/"b"/"wifi-foo.ko").write_bytes(synthetic_module(
        "usb_submit_urb",0x61a2317d))
    # A vendor-specific import is not present in official public GKI.
    (root/"c"/"module-vendor.ko").write_bytes(synthetic_module(
        "motorola_only_symbol",0x1234abcd))
    # A stock module's differing CRC must be reported as a conflict.
    (root/"c"/"bad.ko").write_bytes(synthetic_module(
        "usb_submit_urb",0xabcdef12))
    # Divergent same-name files should not be guessed between.
    (root/"a"/"ambiguous.ko").write_bytes(synthetic_module(
        "foo_unknown",0x11112222))
    (root/"b"/"ambiguous.ko").write_bytes(synthetic_module(
        "foo_unknown",0x33334444))

    public=d/"public.symvers"
    public.write_text("0x61a2317d\tusb_submit_urb\tvmlinux\tEXPORT_SYMBOL_GPL\n"
                      "0x561b7fc2\tieee80211_alloc_hw_nm\tmac80211\tEXPORT_SYMBOL\n")
    report=d/"report.json"
    r=subprocess.run([
        sys.executable,str(INVENTORY),"--offline-dir",str(root),
        "--official-symvers",str(public),"--output",str(report)
    ],capture_output=True,text=True,timeout=25)
    print(r.stdout)
    if r.returncode:
        raise SystemExit(f"CLI failed: {r.stderr}")
    data=json.loads(report.read_text())
    assert data["unique_stock_module_elfs_with_versions"]==3,data
    assert data["skipped_module_reasons"]["different_binaries_same_module_name"]==1
    assert data["crc_pair_categories"]["public_gki_crc_match"]==1
    assert data["crc_pair_categories"]["public_gki_crc_conflict"]==1
    assert data["crc_pair_categories"]["not_in_public_gki"]==1
    assert data["status"].startswith("READ-ONLY")
    assert data["module_mount_paths_collapsed"]>=0
    assert all("binary" not in str(item) for item in data["symbol_records"])
    print("PASS: real CLI creates a JSON inventory, retains distinct CRCs,"
          " and refuses contradictory module versions")
