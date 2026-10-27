#!/usr/bin/env python3
"""Research-only GKI 14563692 *candidate* export-retention superset.

Create a text-only candidate symbol-name whitelist from the **exact public**
Android GKI 14563692 vmlinux.symvers, adding two known missing AR9271 imports.
Cross-check 101 genuine experimental Atheros core import requirements.

NOT the vendor's original ABI symbol list. Not a certified loadable kernel.
No device access, image construction, insmod or kernel configuration change.
"""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

STOCK_SHA256="e3cdaf997a7e2eb70e441944bdfd9af359aa82e8a2d5cb9534d2bce5fcd4a78a"
EXPECTED_GKI_ROWS=8471
EXPECTED_CORE_SYMBOLS=101
MISSING={"rfkill_pause_polling","usb_get_urb"}
EXPECTED_GKI_BUILD="14563692"
NAME=re.compile(r"^[A-Za-z_][A-Za-z_0-9]*$")
HEXCRC=re.compile(r"^0x[0-9A-Fa-f]{8}$")

def load_gki(source):
    exported={}
    for lineno,line in enumerate(source.read_text().splitlines(),1):
        words=line.split()
        if len(words)<3:
            continue
        if words[2]!="vmlinux":
            continue
        if not HEXCRC.fullmatch(words[0]) or not NAME.fullmatch(words[1]):
            raise ValueError(f"Malformed vmlinux symbol row {lineno}: {line[:140]}")
        crc=int(words[0],16)
        symbol=words[1]
        if symbol in exported and exported[symbol]!=crc:
            raise ValueError(f"Inconsistent GKI symbol CRC: {symbol}")
        exported[symbol]=crc
    if len(exported)!=EXPECTED_GKI_ROWS:
        raise ValueError(f"Expected {EXPECTED_GKI_ROWS} unique official GKI vmlinux symbols; got {len(exported)}")
    return exported

def load_manifest(path):
    with path.open(newline="") as f:
        rows=list(csv.DictReader(f,delimiter="\t"))
    if not rows or set(rows[0])!={"symbol","crc"}:
        raise ValueError("Unexpected core-CRC manifest TSV header")
    values={}
    for row in rows:
        symbol=row["symbol"]
        crc=row["crc"]
        if not NAME.fullmatch(symbol) or not HEXCRC.fullmatch(crc):
            raise ValueError(f"Malformed manifest CRC: {row}")
        if symbol in values:
            raise ValueError(f"Duplicate candidate symbol: {symbol}")
        values[symbol]=int(crc,16)
    if len(values)!=EXPECTED_CORE_SYMBOLS:
        raise ValueError(f"Expected {EXPECTED_CORE_SYMBOLS} distinct actual AR9271 core import symbols, got {len(values)}")
    return values

def make_report(gki,required,stock_hash,gki_hash):
    gaps=sorted(set(required)-set(gki))
    mismatches=[{
        "symbol":n,"expected_import_crc":f"0x{required[n]:08x}",
        "official_gki_export_crc":f"0x{gki[n]:08x}"}
        for n in sorted(set(required)&set(gki)) if required[n]!=gki[n]]
    matched=len(set(required)&set(gki))-len(mismatches)
    if set(gaps)!=MISSING:
        raise ValueError(f"Unexpected official GKI missing core exports: {gaps}")
    if mismatches or matched!=99:
        raise ValueError(f"FAIL genuine AR9271 CRC comparisons: {matched} matches; mismatches={mismatches}")
    all_names=set(gki)|MISSING
    if len(all_names)!=EXPECTED_GKI_ROWS+2:
        raise ValueError(f"Unexpected candidate retention count {len(all_names)}")
    return {
        "status":"SOURCE RESEARCH / NOT AUTHORITATIVE VENDOR KMI / NOT FLASHABLE",
        "gki_build_id":EXPECTED_GKI_BUILD,
        "gki_url":"https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers",
        "gki_vmlinux_symvers_sha256":gki_hash,
        "reference_stock_config_sha256":stock_hash,
        "official_gki_unique_vmlinux_exports":len(gki),
        "unique_ar9271_experimental_core_imports":len(required),
        "ar9271_core_imports_matching_official_gki_crc":matched,
        "ar9271_core_imports_with_crc_conflicts":mismatches,
        "missing_from_official_gki":{"symbols":gaps,
          "note":"Functions exist in live kallsyms but no ksymtab export entry observed; must be retained through genuine kernel rebuild, not module hacks."},
        "candidate_retention_unique_names":len(all_names),
        "candidate_retention_names_additional_to_official_gki":sorted(MISSING),
        "proven_vendor_stock_kmi_complete":False,
        "unresolved_reconstruction_gaps":[
           "Original build-time abi_symbollist.raw is missing",
           "Official GKI vmlinux.symvers lists actual *public GKI exports*, not every private vendor allowlisted or phone-customized symbol",
           "Complete normal-boot vendor import inventory is not in repository; 82/101 current live witness matches cannot prove all vendor symbols",
           "Published baseline CRC agreement does not prove modified source or full LTO/CFI compatibility",
           "Experimental module vermagic does not match running kernel release",
           "MODULE_SIG_PROTECT and signing identity remain unresolved",
           "No boot, KernelSU preservation, Wi-Fi, USB OTG, firmware or hardware test completed"
        ],
        "instruction":"This output must not replace the stock KMI whitelist in a bootable kernel build. Do not insmod, flash, patch symbol CRCs or bypass loading policy."
    },all_names

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--gki-symvers",type=Path,required=True)
    p.add_argument("--core-import-manifest",type=Path,required=True)
    p.add_argument("--stock-config",type=Path,required=True)
    p.add_argument("--output-dir",type=Path,required=True)
    args=p.parse_args()
    stock_hash=hashlib.sha256(args.stock_config.read_bytes()).hexdigest()
    if stock_hash!=STOCK_SHA256:
        raise SystemExit("Original user stock Kconfig SHA256 mismatch; refuse")
    stock=args.stock_config.read_text()
    for setting in ("CONFIG_TRIM_UNUSED_KSYMS=y","CONFIG_MODVERSIONS=y",
                    "CONFIG_MODULE_SIG_PROTECT=y","CONFIG_CFI_CLANG=y"):
        if not re.search("^"+re.escape(setting)+"$",stock,re.M):
            raise SystemExit(f"Missing expected stock Kconfig setting: {setting}")
    if not re.search(r'^CONFIG_UNUSED_KSYMS_WHITELIST=".*abi_symbollist.raw"$',stock,re.M):
        raise SystemExit("Unrecognized original stock ABI whitelist configuration")
    gki=load_gki(args.gki_symvers)
    required=load_manifest(args.core_import_manifest)
    gki_hash=hashlib.sha256(args.gki_symvers.read_bytes()).hexdigest()
    report,names=make_report(gki,required,stock_hash,gki_hash)
    args.output_dir.mkdir(parents=True,exist_ok=True)
    allowlist=args.output_dir/"CANDIDATE-RESEARCH-ONLY-NOT-VENDOR-ABI-WHITELIST.txt"
    allowlist.write_text("\n".join(sorted(names))+"\n")
    # Also produce a compact JSON with the CRC of each required published GKI
    # export for reproducibility, *not* with addresses or any vendor ELF bytes.
    report["matched_core_import_crc_evidence"]=[
        {"symbol":name,"gki_export_crc":f"0x{gki[name]:08x}"}
        for name in sorted(set(required)&set(gki))
    ]
    (args.output_dir/"KMI-GKI-14563692-CANDIDATE-EVIDENCE.json").write_text(
        json.dumps(report,indent=2)+"\n")
    print("===== EXACT GKI 14563692 / AR9271 KMI CANDIDATE AUDIT =====")
    print("Official vmlinux exports:",report["official_gki_unique_vmlinux_exports"])
    print("Unique actual AR9271 core imports:",len(required))
    print("Official GKI core CRC matches:",report["ar9271_core_imports_matching_official_gki_crc"])
    print("Official GKI CRC conflicts:",len(report["ar9271_core_imports_with_crc_conflicts"]))
    print("GKI-missing exports:",", ".join(report["missing_from_official_gki"]["symbols"]))
    print("Candidate retained symbol names:",len(names))
    print("CRITICAL: CANDIDATE ONLY. Missing full Motorola vendor ABI whitelist; no loading/flash approval.")
    print("Report:",args.output_dir/"KMI-GKI-14563692-CANDIDATE-EVIDENCE.json")

if __name__=="__main__":
    main()
