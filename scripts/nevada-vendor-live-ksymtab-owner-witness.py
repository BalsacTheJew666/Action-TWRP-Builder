#!/usr/bin/env python3
"""Nevada private read-only corroboration of live ksymtab export OWNER TAGS.

Input: the user's local name-level module attribution JSON (PR #29).
Output: local mode-0600 aggregate and name-level report; only console totals
are intended to be shared. No kernel addresses are saved or printed.

A /proc/kallsyms __ksymtab_* line suffixed by [module] can explicitly witness
that live module as symbol-table owner. An untagged line does NOT by itself
prove a vmlinux export, and neither does an export name prove its CRC.
"""
import argparse
from collections import defaultdict,Counter
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import subprocess

BLOCKERS=("usb_get_urb","rfkill_pause_polling")
IDENT=re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*$")
MODULE_TAG=re.compile(r"^\[([A-Za-z0-9_\-]+)\]$")

def read_readonly(path):
    try:
        return Path(path).read_bytes()
    except OSError:
        response=subprocess.run(["su","-c","cat "+str(path)],
                                capture_output=True,timeout=60,check=False)
        if response.returncode:
            raise RuntimeError("Root-assisted read failed for "+str(path))
        return response.stdout

def parse_modules(blob):
    result=set()
    for line in blob.splitlines():
        bits=line.split()
        if bits:
            name=bits[0].decode("ascii","replace").replace("-","_")
            if IDENT.fullmatch(name):
                result.add(name)
    return result

def parse_export_entries(blob,wanted):
    """Extract names and owner suffix only. Discard addresses and symbol values."""
    result=defaultdict(set)
    export_entries=0
    for line in blob.splitlines():
        p=line.split()
        if len(p)<3:
            continue
        name=p[2].decode("ascii","replace")
        if not name.startswith("__ksymtab_"):
            continue
        export_entries+=1
        symbol=name[len("__ksymtab_"):]
        if symbol not in wanted:
            continue
        owner="NO_MODULE_TAG"
        if len(p)>=4:
            match=MODULE_TAG.fullmatch(p[-1].decode("ascii","replace"))
            if match:
                owner=match.group(1).replace("-","_")
        result[symbol].add(owner)
    return result,export_entries

def make_report(reference,live_owners,loaded,export_entries):
    sought=reference["live_ksymtab_name_unattributed"]
    if not isinstance(sought,list) or len(set(sought))!=len(sought):
        raise ValueError("Invalid/duplicate private attribution names")
    if not all(isinstance(x,str) and IDENT.fullmatch(x) for x in sought):
        raise ValueError("Invalid names in previous private report")
    status={}
    counts=Counter()
    for name in sorted(sought):
        owners=live_owners.get(name,set())
        tagged_loaded=sorted(x for x in owners if x!="NO_MODULE_TAG" and x in loaded)
        tagged_other=sorted(x for x in owners if x!="NO_MODULE_TAG" and x not in loaded)
        no_tag="NO_MODULE_TAG" in owners
        if not owners:
            kind="no_longer_seen_in_kallsyms"
        elif tagged_loaded and not tagged_other and not no_tag:
            kind="explicit_loaded_module_owner"
        elif no_tag and not tagged_loaded and not tagged_other:
            kind="untagged_export_owner_not_proven"
        else:
            kind="ambiguous_or_unrecognized_owner"
        counts[kind]+=1
        status[name]={
            "classification":kind,
            "explicit_live_module_owner_tags":tagged_loaded,
            "other_module_tags":tagged_other,
            "untagged_export_present":no_tag,
            "live_vmlinux_export_proven":False,
            "export_crc_proven":False,
        }
    blockers={}
    for name in BLOCKERS:
        owners=live_owners.get(name,set())
        blockers[name]={
            "ksymtab_name_seen":bool(owners),
            "explicit_live_module_owner_tags":sorted(x for x in owners if x!="NO_MODULE_TAG"),
            "untagged_ksymtab_name_seen":"NO_MODULE_TAG" in owners,
            "real_export_crc_verified":False
        }
    return {
        "status":"PRIVATE READ-ONLY NAME-LEVEL KMI OWNER WITNESS; NOT INSTALLABLE",
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "input_nonpublic_import_names":reference.get("source_stock_inventory_name_count"),
        "previous_unmatched_live_ksymtab_names":len(sought),
        "current_loaded_module_count":len(loaded),
        "total_kallsyms_export_entries_seen":export_entries,
        "owner_classification_counts":dict(sorted(counts.items())),
        "symbol_name_owner_witnesses":status,
        "critical_ar9271_exports":blockers,
        "warnings":[
            "An untagged kallsyms __ksymtab_* line does NOT prove vmlinux ownership.",
            "A tagged module owner identifies the visible module name, not required modversion CRC or live load safety.",
            "An export name is not an authoritative CRC or an ABI whitelist entry.",
            "Do not add all imported module-provided names to vmlinux's KMI whitelist.",
            "Cannot infer vendors' complete abi_symbollist.raw, exact Clang/CFI signing or KernelSU compatibility.",
            "Do not insmod, force-load, patch vermagic/CRC, flash or change system modules."
        ]
    }

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider-report",required=True,type=Path)
    p.add_argument("--output",required=True,type=Path)
    p.add_argument("--kallsyms-file",type=Path,
                   help="CI synthetic fixture only; default is actual /proc/kallsyms")
    p.add_argument("--modules-file",type=Path,
                   help="CI synthetic fixture only; default is actual /proc/modules")
    a=p.parse_args()
    existing=json.loads(a.provider_report.read_text())
    if existing.get("source_stock_inventory_name_count")!=1119:
        raise SystemExit("Refusing report that does not match the reviewed 1119-name private attribution")
    names=set(existing.get("live_ksymtab_name_unattributed",[]))|set(BLOCKERS)
    ksym=read_readonly(a.kallsyms_file or "/proc/kallsyms")
    mods=read_readonly(a.modules_file or "/proc/modules")
    loaded=parse_modules(mods)
    owners,n=parse_export_entries(ksym,names)
    result=make_report(existing,owners,loaded,n)
    os.umask(0o077)
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(a.output,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),"w") as f:
        json.dump(result,f,indent=2)
        f.write("\n")
    os.chmod(a.output,0o600)
    print("NEVADA PRIVATE LIVE KMI OWNER-TAG DIAGNOSTIC — READ ONLY")
    print("Previously unmatched non-public live ksymtab names:",
          result["previous_unmatched_live_ksymtab_names"])
    print("Active kernel modules observed:",len(loaded))
    for kind,count in sorted(result["owner_classification_counts"].items()):
        print(" ",kind+":",count)
    print("AR9271 missing kernel exports:",result["critical_ar9271_exports"])
    print("Private local output:",a.output)
    print("Owner tags do not prove kernel export CRCs or device module loadability. NO FLASH.")

if __name__=="__main__":
    main()
