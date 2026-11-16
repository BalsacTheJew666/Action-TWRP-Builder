#!/usr/bin/env python3
"""READ-ONLY local provider classification for Nevada's vendor ABI import inventory.

Uses only the already generated local vendor-private-kmi-inventory.json plus
already-loaded stock module ELF files. Reports whether each public-GKI-absent
import is exported by an on-disk, already-loaded module, not whether vmlinux
exports it. A source ELF candidate is not an authenticated live-module image.

NO uploading, kernel writes, insmod, modprobe, flashing, KMI changes or root
configuration changes. Detailed report saved ONLY to Termux (0600).
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import struct
import sys

BASE_GKI_SHA256="bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0"
KNOWN_TWO={"rfkill_pause_polling","usb_get_urb"}
MAX_MODULE_MIB=64

def import_helper(path):
    spec=importlib.util.spec_from_file_location("nevada_witness_export_helper",str(path))
    if not spec or not spec.loader:
        raise ValueError("Cannot import reviewed witness script")
    helper=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    for key in ("read","scan","scan_as_root","select_matching_module","STOCK_DIRS"):
        if not hasattr(helper,key):
            raise ValueError("Outdated witness helper: "+key)
    return helper

def parsed_sections(raw):
    """Parse section headers with strict offsets and bounds for ELF64 LE."""
    if len(raw)<64 or raw[:6]!=b"\x7fELF\x02\x01":
        raise ValueError("Expected ELF64 little-endian .ko")
    off=struct.unpack_from("<Q",raw,40)[0]
    ent,num,shstr=struct.unpack_from("<HHH",raw,58)
    if ent!=64 or not (1<=num<=16384) or shstr>=num or off+num*ent>len(raw):
        raise ValueError("Invalid ELF64 section header table")
    secs=[]
    for idx in range(num):
        s=struct.unpack_from("<IIQQQQIIQQ",raw,off+idx*ent)
        if s[1]!=8 and s[4]+s[5]>len(raw):  # SHT_NOBITS doesn't occupy bytes
            raise ValueError("ELF section exceeds file")
        secs.append(s)
    sh=secs[shstr]
    if sh[1]!=3:
        raise ValueError("Invalid ELF shstrtab")
    names=raw[sh[4]:sh[4]+sh[5]]
    def cstr(data,start):
        if start>=len(data):
            return ""
        return data[start:].split(b"\x00",1)[0].decode("ascii","replace")
    return secs,[(cstr(names,s[0]),s) for s in secs],cstr

def exports_from_elf(raw,interesting):
    """Only defined __ksymtab_NAME symbols count as confirmed ELF declarations.

    __ksymtab_strings alone are weak evidence: report them separately when
    .symtab is missing or stripped. A __crc_NAME ABS value is optional and
    independently checked against the stock importer's recorded CRC demand.
    """
    secs,named,cstr=parsed_sections(raw)
    exports={}
    export_crcs={}
    scanned_symtab=False
    for name,s in named:
        if s[1]!=2:     # SHT_SYMTAB
            continue
        scanned_symtab=True
        if s[6]>=len(secs):
            raise ValueError("Broken ELF symbol string-table link")
        strsec=secs[s[6]]
        if strsec[1]!=3:
            raise ValueError("ELF symtab strtab is not SHT_STRTAB")
        strings=raw[strsec[4]:strsec[4]+strsec[5]]
        stride=s[9] or 24
        if stride!=24 or s[5]%stride!=0:
            raise ValueError("Bad ELF64 symbol table entry length")
        for offset in range(s[4],s[4]+s[5],stride):
            str_off,info,other,shndx,value,symsize=struct.unpack_from("<IBBHQQ",raw,offset)
            sym=cstr(strings,str_off)
            if shndx==0 or not sym:
                continue
            if sym.startswith("__ksymtab_"):
                export_name=sym[len("__ksymtab_"):]
                if export_name in interesting:
                    exports[export_name]="defined_ksymtab_symbol"
            elif sym.startswith("__crc_") and shndx==0xfff1: # SHN_ABS
                export_name=sym[len("__crc_"):]
                if export_name in interesting:
                    crc=value&0xffffffff
                    if export_name in export_crcs and export_crcs[export_name]!=crc:
                        raise ValueError("Conflicting export CRCs within one module")
                    export_crcs[export_name]=crc
    weak=set()
    for name,s in named:
        if name!="__ksymtab_strings" or s[1]!=1:
            continue
        block=raw[s[4]:s[4]+s[5]]
        all_strings=set(x.decode("ascii","replace") for x in block.split(b"\x00") if x)
        weak|=all_strings&interesting
    # Only associate CRCs with symbols that have a source ELF export declaration.
    export_crcs={name:crc for name,crc in export_crcs.items() if name in exports}
    return exports,export_crcs,weak-exports.keys(),scanned_symtab

def classify_inventory(stock_inventory,exporters,weak_exporters,unreadable):
    inventory=stock_inventory["symbol_inventory"]
    all_absent={name for name,row in inventory.items()
                if row["bucket"]=="not_an_official_public_gki_vmlinux_export"}
    targets=all_absent-KNOWN_TWO
    saved_targets=set(stock_inventory["names_not_in_8473_public_plus_two_candidate"])
    if targets!=saved_targets:
        raise RuntimeError("Input inventory candidate-name list is internally inconsistent")
    result={}
    statuses=Counter()
    matched_crc=0
    crc_conflicts=0
    for symbol in sorted(targets):
        modules=sorted(set(exporters.get(symbol,{})))
        weaker=sorted(set(weak_exporters.get(symbol,()))-set(modules))
        imports={int(v,16) for v in inventory[symbol]["distinct_import_crcs"]}
        verified_crc={}
        for mod in modules:
            crc=exporters[symbol][mod]
            if crc is not None:
                verified_crc[mod]=f"0x{crc:08x}"
                if crc in imports:
                    matched_crc+=1
                else:
                    crc_conflicts+=1
        if len(modules)>1:
            status="multiple_loaded_module_ELF_declarations"
        elif len(modules)==1:
            status="one_loaded_module_ELF_declaration"
        elif weaker:
            status="only_ksymtab_strings_candidate"
        else:
            status="no_provider_seen_among_readable_loaded_modules"
        statuses[status]+=1
        result[symbol]={
          "classification":status,
          "loaded_module_ELF_export_declarations":modules,
          "weak_ksymtab_strings_only_module_candidates":weaker,
          "provider_export_abs_crc_when_present":verified_crc,
          "imported_crc_requirements":sorted(f"0x{c:08x}" for c in imports),
        }
    return result,dict(sorted(statuses.items())),{
        "available_export_crc_comparisons_matching":matched_crc,
        "available_export_crc_comparisons_conflicting":crc_conflicts,
        "stock_modules_skipped_count":len(unreadable),
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--inventory-json",type=Path,required=True)
    p.add_argument("--witness-script",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--offline-dir",type=Path,help="CI synthetic test ONLY: no root calls")
    a=p.parse_args()
    data=json.loads(a.inventory_json.read_text())
    if data.get("official_gki_reference_sha256")!=BASE_GKI_SHA256:
        raise SystemExit("Refusing unknown official public GKI reference")
    if data.get("mode") not in ("normal_boot_private_device","offline_CI_synthetic"):
        raise SystemExit("Refusing unknown import inventory mode")
    if not isinstance(data.get("symbol_inventory"),dict):
        raise SystemExit("No symbol inventory in local JSON")
    if data.get("mode")=="normal_boot_private_device" and a.offline_dir:
        raise SystemExit("Do not mix normal-boot import results with offline test modules")
    if data.get("mode")=="offline_CI_synthetic" and not a.offline_dir:
        raise SystemExit("Synthetic inventory requires --offline-dir")
    if a.report.resolve()==a.inventory_json.resolve():
        raise SystemExit("Refuse to overwrite original private import inventory")

    helper=import_helper(a.witness_script)
    if a.offline_dir:
        wanted={x.stem.replace("-","_") for x in a.offline_dir.rglob("*.ko")}
        dirs=[str(a.offline_dir)]
    else:
        loaded=helper.read("/proc/modules")
        if not loaded:
            raise SystemExit("Cannot read /proc/modules")
        wanted={ln.split()[0].decode().replace("-","_")
                for ln in loaded.splitlines() if ln.split()}
        dirs=helper.STOCK_DIRS
    found=helper.scan(dirs,wanted)
    root_status={"status":"CI_offline_no_root"}
    if not a.offline_dir:
        root,root_status=helper.scan_as_root(dirs,wanted)
        for name,paths in root.items():
            found[name].extend(paths)
    target=set(data["names_not_in_8473_public_plus_two_candidate"])
    exporters=defaultdict(dict)
    weak=defaultdict(set)
    skipped={}
    selected=0
    with_symtab=0
    for name in sorted(wanted):
        paths=found.get(name,[])
        if not paths:
            skipped[name]="module_ELF_not_found"
            continue
        raw,status,_=helper.select_matching_module(paths)
        if raw is None:
            skipped[name]=status
            continue
        if len(raw)>MAX_MODULE_MIB*1048576:
            skipped[name]="ELF_unexpectedly_large"
            continue
        try:
            definitions,crcs,weaker,symtab=exports_from_elf(raw,target)
        except (ValueError,IndexError,UnicodeError,OverflowError,struct.error):
            skipped[name]="invalid_ELF_export_tables"
            continue
        selected+=1
        with_symtab+=int(symtab)
        for symbol in definitions:
            exporters[symbol][name]=crcs.get(symbol)
        for symbol in weaker:
            weak[symbol].add(name)
    result,statuses,crc_summary=classify_inventory(data,exporters,weak,skipped)
    full={
        "status":"PRIVATE READ-ONLY LOADED STOCK MODULE EXPORT CANDIDATES; NOT AN AUTHENTIC KERNEL KMI",
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "mode":"offline_CI_synthetic" if a.offline_dir else "normal_boot_private_device",
        "reference_private_import_inventory":str(a.inventory_json),
        "module_ELFs_examined":selected,
        "module_ELFs_with_symtab":with_symtab,
        "loaded_module_names":len(wanted),
        "root_module_enumeration":root_status,
        "skipped_module_names_by_reason":dict(Counter(skipped.values())),
        "public_GKI_absent_imported_names_examined":len(result),
        "result_buckets":statuses,
        "export_crc_comparison":crc_summary,
        "provider_candidates":result,
        "critical_caveats":[
            "This classifies only exported names declared in already-loaded on-disk module ELF candidates; not live confirmed providers.",
            "Unresolved imported names might be vmlinux exports, unloaded modules, omitted proprietary modules, or missing paths.",
            "Do NOT treat absent-public-GKI names as core vmlinux exports or append them en masse to a KMI whitelist.",
            "An ELF __crc_ABS value when present is compared as additional evidence but does not prove the device's live exported CRC.",
            "Original Motorola vendor abi_symbollist.raw, stock FullLTO/CFI/signing and exact kernelrelease remain unverified.",
            "Two AR9271 blockers usb_get_urb and rfkill_pause_polling still require a correctly compiled kernel and valid all-vendor KMI.",
            "Never insmod, flash, change SELinux, KernelSU, recovery or internal Wi-Fi based on this research."
        ],
    }
    os.umask(0o077)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(a.report,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),
                   "w",encoding="utf-8") as fp:
        json.dump(full,fp,indent=2)
        fp.write("\n")
    os.chmod(a.report,0o600)
    print("===== MOTOROLA NEVADA PRIVATE MODULE-EXPORT PROVIDER AUDIT =====")
    print("Loaded module candidate ELFs read:",selected,"/",len(wanted))
    print("Module ELF files with symtab:",with_symtab)
    print("Imported names missing public GKI (+2 excluded):",len(result))
    for k,v in sorted(statuses.items()):
        print(" ",k+":",v)
    print("Available provider-CRC matches:",crc_summary["available_export_crc_comparisons_matching"])
    print("Available provider-CRC conflicts:",crc_summary["available_export_crc_comparisons_conflicting"])
    print("Modules skipped (by reason):",full["skipped_module_names_by_reason"])
    print("Private detailed report:",a.report)
    print("DO NOT ASSUME unresolved names are kernel exports. No kernel changes.")

if __name__=="__main__":
    main()
