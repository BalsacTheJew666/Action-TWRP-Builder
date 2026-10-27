#!/usr/bin/env python3
"""Read-only AR9271 kernel export CRC check using exact public GKI build symvers.

Inputs (NO module installation):
  1. Directory holding four experimental Atheros .ko files from CI #40413637325.
  2. Official GKI vmlinux.symvers from android13-5.15-2025-05_r14
     artifact build 14563692 (uname -r ends in -ab14563692).
  3. Previously SHA256-verified 30-import stock Wi-Fi reference CSV.
  4. Output directory.

This independently compares *candidate driver* imports against Google's
release-binary exported CRC data; it is NOT a live phone KMI verification.
"""
from collections import Counter
import csv
import json
from pathlib import Path
import re
import struct
import subprocess
import sys

DRIVERS=("ath.ko","ath9k_hw.ko","ath9k_common.ko","ath9k_htc.ko")
TARGET="ieee80211_alloc_hw_nm"
EXPECTED_WIFI_CRC=0x561b7fc2
EXPECTED_CORE_IMPORTS=136

def readelf(path, *args):
    return subprocess.run(["readelf",*args,str(path)],check=True,
                          capture_output=True,text=True).stdout

def section(path, name):
    # parse readelf -SW, not fixed-position section indices
    for line in readelf(path,"-SW").splitlines():
        p=line.split()
        if name not in p:
            continue
        idx=p.index(name)
        if len(p)<idx+5:
            raise ValueError(f"Malformed section header for {name}: {line}")
        offset=int(p[idx+3],16)
        size=int(p[idx+4],16)
        data=path.read_bytes()
        if offset+size>len(data):
            raise ValueError("ELF section exceeds file")
        return data[offset:offset+size]
    raise ValueError(f"Missing {name} in {path}")

def versions(path):
    raw=section(path,"__versions")
    if len(raw)%64:
        raise ValueError(f"Bad __versions width in {path}")
    out={}
    for i in range(0,len(raw),64):
        crc=struct.unpack_from("<Q",raw,i)[0]&0xffffffff
        name=raw[i+8:i+64].split(b"\0",1)[0].decode("ascii")
        if name:
            if name in out and out[name]!=crc:
                raise ValueError(f"Conflicting CRC for {name} in {path}")
            out[name]=crc
    return out

def export_crcs(path):
    result={}
    for line in readelf(path,"-sW").splitlines():
        p=line.split()
        if len(p)>=8 and p[-2]=="ABS" and p[-1].startswith("__crc_"):
            result[p[-1][6:]]=int(p[1],16)&0xffffffff
    return result

def parse_symvers(path, provider="vmlinux"):
    data={}
    for row in path.read_text(errors="replace").splitlines():
        p=row.split()
        if len(p)<3 or p[2]!=provider:
            continue
        if not re.fullmatch(r"0x[0-9a-fA-F]{8}",p[0]):
            raise ValueError(f"Malformed {provider} CRC row: {row[:120]}")
        name=p[1];crc=int(p[0],16)
        if name in data and data[name]!=crc:
            raise ValueError(f"Duplicate incompatible CRC for {name}")
        data[name]=crc
    if len(data)<1000:
        raise ValueError(f"Unexpectedly small {provider} symvers: {len(data)} symbols")
    return data

def load_wifi_csv(path):
    rows=list(csv.DictReader(path.open()))
    if len(rows)!=30:
        raise ValueError(f"Expected exactly 30 saved stock Wi-Fi import rows, got {len(rows)}")
    reference={}
    for row in rows:
        if set(row)!={"driver","symbol","import_crc","stock_crc"}:
            raise ValueError("Unexpected stock Wi-Fi CSV schema")
        key=(row["driver"],row["symbol"])
        if key in reference:
            raise ValueError(f"Duplicate Wi-Fi reference: {key}")
        reference[key]=int(row["stock_crc"],16)
    if reference.get(("ath9k_htc.ko",TARGET))!=EXPECTED_WIFI_CRC:
        raise ValueError("Stock mac80211 CRC record missing or changed")
    return reference

def main():
    if len(sys.argv)!=5:
        raise SystemExit(__doc__)
    mods_dir, official_file, wifi_csv, report_dir=map(Path,sys.argv[1:])
    report_dir.mkdir(parents=True,exist_ok=True)
    official=parse_symvers(official_file)
    stock_wifi=load_wifi_csv(wifi_csv)
    candidates={}
    for name in DRIVERS:
        p=mods_dir/name
        if not p.is_file() or p.read_bytes()[:4]!=b"\x7fELF":
            raise ValueError(f"Missing/invalid experimental ELF module {p}")
        candidates[name]=p

    ath_exports={}
    for name,path in candidates.items():
        for symbol,crc in export_crcs(path).items():
            ath_exports.setdefault(symbol,(name,crc))

    summary=Counter()
    all_rows=[]
    for name,path in candidates.items():
        for symbol,actual in sorted(versions(path).items()):
            provider=None
            verified_crc=None
            status=None
            if (name,symbol) in stock_wifi:
                verified_crc=stock_wifi[name,symbol]
                provider="saved-stock-wifi-elf-export"
                status="stock_wifi_match" if actual==verified_crc else "stock_wifi_mismatch"
            elif symbol in ath_exports:
                provider,verified_crc=ath_exports[symbol]
                status="experimental_atheros_match" if actual==verified_crc else "experimental_atheros_mismatch"
            elif symbol in official:
                provider="official-GKI-14563692-vmlinux.symvers"
                verified_crc=official[symbol]
                status="official_core_match" if actual==verified_crc else "official_core_mismatch"
            else:
                provider="unknown/unverified"
                status="core_not_exported_by_official_gki"
            summary[status]+=1
            all_rows.append({
                "module":name,"symbol":symbol,"import_crc":f"0x{actual:08x}",
                "reference_crc":None if verified_crc is None else f"0x{verified_crc:08x}",
                "provider":provider,"status":status
            })
    core_rows=[x for x in all_rows if x["status"].startswith("official_core_") or x["status"]=="core_not_exported_by_official_gki"]
    mismatch=[x for x in all_rows if x["status"].endswith("_mismatch") or x["status"]=="core_not_exported_by_official_gki"]
    result={
      "status":"RESEARCH-ONLY; NOT A DEVICE MODULE LOAD APPROVAL",
      "core_reference":"Official Google Android GKI kernel_aarch64 build 14563692 vmlinux.symvers",
      "source_revision":"9b2308ac0ad616788fb57ba688aa07f0ff221355",
      "gki_reference_symbol_count":len(official),
      "total_imports":len(all_rows),
      "saved_stock_wifi_import_references":len(stock_wifi),
      "expected_previously_experimental_core_imports":EXPECTED_CORE_IMPORTS,
      "tested_core_or_missing_imports":len(core_rows),
      "summary":dict(sorted(summary.items())),
      "mismatch_count":len(mismatch),
      "mismatches_or_missing":mismatch,
      "records":all_rows,
      "important_limitation":"Official GKI release ABI is a strongly grounded reference for the matching base build; cannot establish Motorola's live core exports, module vermagic, CFI, signature policy, USB or firmware; never insmod/flash these experimental modules."
    }
    (report_dir/"official-gki-core-crc-audit.json").write_text(json.dumps(result,indent=2)+"\n")
    lines=[
      "AR9271 OFFICIAL GKI 14563692 ABI REFERENCE (DIAGNOSTIC ONLY)",
      f"Official exported core CRCs parsed: {len(official)}",
      f"Total Atheros imported entries: {len(all_rows)}",
      *[f"{k}: {v}" for k,v in sorted(summary.items())],
      f"Core- or missing-reference imports: {len(core_rows)} (previously 136 candidate-core imports)",
      f"Mismatch/unresolved entries: {len(mismatch)}",
      "IMPORTANT: no actual handset module loading, core CRC extraction, signature, CFI, or vermagic verified.",
      "DO NOT FLASH, INSMOD, OR INSTALL THIS EXPERIMENTAL DRIVER."
    ]
    txt="\n".join(lines)+"\n"
    (report_dir/"README-OFFICIAL-GKI-CORE-RESULTS.txt").write_text(txt)
    print(txt)
    if summary["stock_wifi_mismatch"] or summary["experimental_atheros_mismatch"]:
        raise SystemExit("FAIL: already verified Wi-Fi or Atheros self-consistency regressed")
    # Core mismatches are a genuine outcome to report, not a failure of the checker.
    # CI still completes, with a clear red outcome inside summary and JSON.
    print("Comparison completed; check report for official kernel CRC mismatches.")

if __name__=="__main__":
    main()
