#!/usr/bin/env python3
"""READ-ONLY stock-module import inventory for Motorola XT2615-1 (nevada).

System access: /proc/modules, existing on-disk .ko files via the pinned
read-only witness.py helpers, optional KernelSU read-only 'find' and 'cat'.
Writes only a local JSON report under Termux; does NOT upload device data,
load modules, change root/SELinux, flash, write to system, or build a kernel.

The imported-symbol CRCs from vendor .ko are *requirements*, not proof of
kernel exports. Module-to-module imports are intentionally left unclassified.
"""
import argparse
from collections import defaultdict
import csv
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
from datetime import datetime,timezone

GKI_SHA256="bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0"
GKI_COUNT=8471
KNOWN_MISSING=("rfkill_pause_polling","usb_get_urb")

def import_witness(path):
    spec=importlib.util.spec_from_file_location("nevada_kmi_witness",str(path))
    if not spec or not spec.loader:
        raise RuntimeError(f"Cannot load read-only witness helper: {path}")
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("read","imports","scan","scan_as_root","select_matching_module","STOCK_DIRS"):
        if not hasattr(module,name):
            raise RuntimeError(f"Witness helper is outdated (missing {name}); re-download approved current script")
    return module

def read_public_gki(path):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=GKI_SHA256:
        raise RuntimeError("Official GKI symvers SHA256 mismatch; refuse comparison")
    symbols={}
    for line in path.read_text().splitlines():
        words=line.split()
        if len(words)<3 or words[2]!="vmlinux":
            continue
        if not re.fullmatch(r"0x[0-9a-fA-F]{8}",words[0]):
            raise ValueError(f"Invalid official GKI CRC row: {line[:100]}")
        name,crc=words[1],int(words[0],16)
        if name in symbols and symbols[name]!=crc:
            raise ValueError("Conflicting official CRC: "+name)
        symbols[name]=crc
    if len(symbols)!=GKI_COUNT:
        raise RuntimeError(f"Unexpected public GKI export count {len(symbols)}")
    return symbols

def load_core_manifest(path):
    values={}
    with path.open(newline="") as f:
        rows=list(csv.DictReader(f,delimiter="\t"))
    if len(rows)!=101:
        raise ValueError("Required AR9271 core import TSV changed")
    for row in rows:
        name=row["symbol"]
        if name in values:
            raise ValueError(f"Duplicate core requirement: {name}")
        values[name]=int(row["crc"],16)
    return values

def build_summary(importers,gki,core,examined,discovery,skipped):
    # Each distinct symbol can be imported by multiple stock modules.
    # Do not assume unlisted names are kernel-core exports: some providers are
    # modules (including stock mac80211/cfg80211 and Motorola/vendor modules).
    detail={}
    bucket_counts=defaultdict(int)
    crc_instances=0
    for name,items in sorted(importers.items()):
        crcs=sorted({r["crc_int"] for r in items})
        if len(crcs)>1:
            bucket="conflicting_stock_import_requirements"
        elif name not in gki:
            bucket="not_an_official_public_gki_vmlinux_export"
        elif crcs[0]!=gki[name]:
            bucket="differs_from_official_public_gki_crc"
        else:
            bucket="matches_official_public_gki_crc"
        bucket_counts[bucket]+=1
        crc_instances+=len(items)
        detail[name]={
          "bucket":bucket,
          "distinct_import_crcs":[f"0x{v:08x}" for v in crcs],
          "official_public_gki_crc":f"0x{gki[name]:08x}" if name in gki else None,
          "loaded_stock_module_importers":sorted({r["module"] for r in items}),
          "import_instances":len(items),
        }
    matched_core={}
    conflicted_core={}
    for name,required in core.items():
        if name not in detail:
            continue
        seen={int(x,16) for x in detail[name]["distinct_import_crcs"]}
        if seen=={required}:
            matched_core[name]=f"0x{required:08x}"
        else:
            conflicted_core[name]={
              "required":f"0x{required:08x}",
              "stock_import_crcs":sorted(f"0x{x:08x}" for x in seen)
            }
    gaps=sorted(set(core)-set(matched_core)-set(conflicted_core))
    candidates=sorted(set(detail)-set(gki)-set(KNOWN_MISSING))
    report={
      "status":"READ-ONLY STOCK MODULE IMPORT WITNESSES; NOT AUTHORITATIVE KERNEL EXPORTS",
      "timestamp_utc":datetime.now(timezone.utc).isoformat(),
      "running_kernel_release":os.uname().release,
      "official_gki_build_id":"14563692",
      "official_public_gki_vmlinux_exports":len(gki),
      "official_gki_reference_sha256":GKI_SHA256,
      "already_loaded_module_elfs_examined":examined,
      "loaded_module_discovery":discovery,
      "skipped_module_names_by_reason":skipped,
      "distinct_imported_symbol_names":len(detail),
      "total_import_records":crc_instances,
      "imported_symbol_buckets":dict(sorted(bucket_counts.items())),
      "names_not_in_8473_public_plus_two_candidate_count":len(candidates),
      "names_not_in_8473_public_plus_two_candidate":candidates,
      "core_101_symbol_witnesses_matching":len(matched_core),
      "core_101_symbol_witnesses_conflicting":len(conflicted_core),
      "core_101_symbol_witnesses_without_evidence":len(gaps),
      "core_101_no_witness_symbol_names":gaps,
      "core_101_conflicts":conflicted_core,
      "required_blockers":{
        name:{
          "stock_module_import_seen":name in detail,
          "public_GKI_core_export_present":name in gki,
          "actual_live_export_proven":False
        } for name in KNOWN_MISSING
      },
      "symbol_inventory":detail,
      "privacy":"REPORT STAYS IN TERMUX. Do not upload raw stock module binaries or private firmware to public GitHub. You can share only the printed summary.",
      "limitations":[
        "Loaded stock module imports do NOT prove the running kernel exports any CRC.",
        "An import absent from public GKI may be provided by another stock kernel module rather than vmlinux; do NOT append names blindly to a kernel whitelist.",
        "This inventories only modules with matching on-disk ELFs loaded in the current boot; missing/built-in/unloaded module dependencies are not covered.",
        "The authentic Motorola original abi_symbollist.raw remains unavailable.",
        "Two AR9271 required core exports usb_get_urb and rfkill_pause_polling remain unavailable in official GKI and not seen as live ksymtab entries.",
        "No installation or flashing authorization; mismatched module vermagic, signatures and CFI remain."
      ]
    }
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--witness-script",type=Path,required=True,
                   help="Known, already reviewed read-only live witness script")
    p.add_argument("--official-gki-symvers",type=Path,required=True)
    p.add_argument("--core-import-manifest",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--offline-dir",type=Path,
                   help="CI-only offline synthetic module directory (no root)")
    args=p.parse_args()
    gki=read_public_gki(args.official_gki_symvers)
    required=load_core_manifest(args.core_import_manifest)
    witness=import_witness(args.witness_script)
    offline=args.offline_dir is not None
    if offline:
        directories=[str(args.offline_dir)]
        wanted={p.stem.replace("-","_") for p in args.offline_dir.rglob("*.ko")}
    else:
        raw=witness.read("/proc/modules")
        if not raw:
            raise SystemExit("Cannot read /proc/modules. Root may be required.")
        wanted={ln.split()[0].decode().replace("-","_") for ln
                in raw.splitlines() if ln.split()}
        directories=witness.STOCK_DIRS
    found=witness.scan(directories,wanted)
    root_scan={"status":"not_needed_for_offline_test"}
    if not offline:
        root_paths,root_scan=witness.scan_as_root(directories,wanted)
        for name,paths in root_paths.items():
            found[name].extend(paths)
    discovered={"loaded_module_names":len(wanted),
                "matched_unprivileged_and_rooted_paths":sum(map(len,found.values())),
                "root_read_only_discovery":root_scan}
    skipped=defaultdict(list)
    importers=defaultdict(list)
    examined=0
    for name in sorted(wanted):
        paths=found.get(name,[])
        if not paths:
            skipped["not_found"].append(name)
            continue
        blob,status,_=witness.select_matching_module(paths)
        if blob is None:
            skipped[status].append(name)
            continue
        try:
            imports=witness.imports(blob)
        except (ValueError,IndexError,UnicodeError,OverflowError) as e:
            skipped["invalid_elf_parser"].append(name)
            continue
        examined+=1
        for symbol,crc in imports.items():
            importers[symbol].append({"module":name,"crc_int":crc})
    report=build_summary(importers,gki,required,examined,discovered,dict(skipped))
    report["mode"]="offline_CI_synthetic" if offline else "normal_boot_private_device"
    # Keep local output readable only to the Termux owner by default.
    os.umask(0o077)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    args.report.write_text(json.dumps(report,indent=2)+"\n")
    print("===== MOTOROLA NEVADA LOCAL PRIVATE VENDOR ABI IMPORT INVENTORY =====")
    print("Mode:",report["mode"])
    print("Kernel:",report["running_kernel_release"])
    print("Loaded module ELFs read:",examined,"/",len(wanted))
    print("Distinct imported symbols:",report["distinct_imported_symbol_names"])
    for key,value in sorted(report["imported_symbol_buckets"].items()):
        print("  "+key+":",value)
    print("Names absent from 8473-name PUBLIC candidate (may be module-provided):",
          report["names_not_in_8473_public_plus_two_candidate_count"])
    print("AR9271 core requirement witnesses:",
          report["core_101_symbol_witnesses_matching"],"matching,",
          report["core_101_symbol_witnesses_conflicting"],"conflicting,",
          report["core_101_symbol_witnesses_without_evidence"],"not witnessed")
    print("Missing official GKI core export names:",", ".join(KNOWN_MISSING))
    print("Stored full symbol inventory privately at:",args.report)
    print("NOT a complete vendor KMI whitelist. NO module-load/flash permission.")

if __name__=="__main__":
    main()
