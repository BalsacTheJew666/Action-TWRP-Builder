#!/usr/bin/env python3
"""XT2615-1 Nevada PRIVATE read-only owner-to-ELF/CRC crosscheck.

Inputs are locally saved PRIVATE reports from the 1006->742+264 triage and the
existing reviewed witness.py/provider ELF parser. The only device reads are
/proc/modules and already installed .ko files through existing read-only
KernelSU find/cat helpers. No uploading any report, raw ELF or user data.
A disk candidate's CRC is not the active live provider's authoritative CRC.
"""
import argparse
from collections import Counter,defaultdict
from datetime import datetime,timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import sys

BLOCKERS=("rfkill_pause_polling","usb_get_urb")
IDENT=re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
EXPECTED=264

def helper(path,needed):
    spec=importlib.util.spec_from_file_location("nevada_private_helper_"+path.stem.replace("-","_"),str(path))
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot read source-only helper {path}")
    obj=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(obj)
    for fn in needed:
        if not hasattr(obj,fn):
            raise RuntimeError(f"Reviewed helper missing {fn}: {path}")
    return obj

def inputs(triage,provider):
    rows=triage.get("unresolved_name_details")
    if (triage.get("unresolved_names_checked")!=EXPECTED or
        not isinstance(rows,dict) or len(rows)!=EXPECTED or
        triage.get("classification_counts",{}).get("live_loaded_module_owner_tag")!=EXPECTED):
        raise ValueError("Refusing triage without all 264 live-module owner tags")
    inventory=provider.get("provider_candidates")
    if not isinstance(inventory,dict) or len(inventory)!=1006:
        raise ValueError("Refusing unrecognized original 1006-name provider report")
    out={}
    for name,entry in rows.items():
        if not IDENT.fullmatch(name) or entry.get("status")!="live_loaded_module_owner_tag":
            raise ValueError("Invalid owner-tag classification")
        owners=entry.get("loaded_module_owner_tags")
        if not isinstance(owners,list) or not owners or len(owners)!=len(set(owners)):
            raise ValueError("Missing/duplicate owner tag")
        if not all(isinstance(owner,str) and IDENT.fullmatch(owner) for owner in owners):
            raise ValueError("Invalid loaded module name")
        p=inventory.get(name)
        if not isinstance(p,dict) or p.get("classification")!="no_provider_seen_among_readable_loaded_modules":
            raise ValueError("Original provider entry inconsistent for "+name)
        required=p.get("imported_crc_requirements")
        if not isinstance(required,list) or not required or len(set(required))!=len(required):
            raise ValueError("Missing CRC import requirements")
        try:
            crcs={int(x,16) for x in required}
        except (TypeError,ValueError):
            raise ValueError("Bad CRC value")
        if any(x<0 or x>0xffffffff for x in crcs):
            raise ValueError("Bad CRC width")
        out[name]={"owners":owners,"required":crcs}
    if set(out)!=set(name for name,e in inventory.items() if e.get("classification")=="no_provider_seen_among_readable_loaded_modules"):
        raise ValueError("Triage names differ from original provider inventory")
    return out

def classify(rows,owners_seen,owner_elf):
    """Pure categorizer. 'matches' below are DISK candidate CRC references only."""
    classifications=Counter()
    owner_results=Counter()
    records={}
    for sym,requirement in sorted(rows.items()):
        checks=[]
        for owner in requirement["owners"]:
            if owner not in owners_seen:
                status="owner_no_longer_loaded"
                value=None
            elif owner not in owner_elf:
                status="no_matching_on_disk_elf"
                value=None
            else:
                data=owner_elf[owner]
                status=data.get("status","unavailable")
                value=None
                if status=="parsed":
                    export=data["export_names"]
                    crc_map=data["export_crcs"]
                    if sym not in export:
                        status="not_declared_in_readable_elf"
                    elif sym not in crc_map:
                        status="elf_export_abs_crc_not_present"
                    else:
                        value=crc_map[sym]
                        status=("candidate_elf_crc_matches_import" if value in requirement["required"]
                                else "candidate_elf_crc_conflicts_with_import")
            owner_results[status]+=1
            checks.append({"owner_module":owner,"status":status,
                           "candidate_elf_crc":None if value is None else f"0x{value:08x}"})
        statuses={e["status"] for e in checks}
        if "candidate_elf_crc_conflicts_with_import" in statuses:
            category="candidate_elf_crc_conflict_needs_manual_review"
        elif statuses=={"candidate_elf_crc_matches_import"}:
            category="all_owner_candidate_elf_crcs_match_imports"
        elif "candidate_elf_crc_matches_import" in statuses:
            category="partial_candidate_elf_crc_match"
        elif "elf_export_abs_crc_not_present" in statuses:
            category="elf_declared_export_without_crc"
        else:
            category="owner_tag_only_or_disk_elf_missing"
        classifications[category]+=1
        records[sym]={
           "classification":category,
           "required_stock_import_crcs":[f"0x{x:08x}" for x in sorted(requirement["required"])],
           "owners":checks,
           "live_core_export_crc_verified":False,
        }
    return dict(sorted(classifications.items())),dict(sorted(owner_results.items())),records

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--triage-report",type=Path,required=True)
    p.add_argument("--provider-report",type=Path,required=True)
    p.add_argument("--witness-script",type=Path,required=True)
    p.add_argument("--elf-parser-script",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    a=p.parse_args()
    if a.report.resolve() in (a.triage_report.resolve(),a.provider_report.resolve()):
        raise SystemExit("Refusing to overwrite existing evidence")
    triage=json.loads(a.triage_report.read_text())
    provider=json.loads(a.provider_report.read_text())
    rows=inputs(triage,provider)
    witness=helper(a.witness_script,("read","scan","scan_as_root","select_matching_module","STOCK_DIRS"))
    decoder=helper(a.elf_parser_script,("exports_from_elf",))
    live=witness.read("/proc/modules")
    if not live:
        raise SystemExit("Cannot read live /proc/modules; no classification attempted")
    loaded={x.split()[0].decode("ascii","replace").replace("-","_")
            for x in live.splitlines() if x.split()}
    target_owners={owner for r in rows.values() for owner in r["owners"]}
    found=witness.scan(witness.STOCK_DIRS,target_owners)
    from_root,root_status=witness.scan_as_root(witness.STOCK_DIRS,target_owners)
    for name,paths in from_root.items():
        found[name].extend(paths)
    owner_elf={}
    unreadable=[]
    for owner in sorted(target_owners&loaded):
        paths=found.get(owner,[])
        if not paths:
            continue
        raw,status,_=witness.select_matching_module(paths,reader=witness.read)
        if raw is None:
            owner_elf[owner]={"status":"elf_"+status}
            unreadable.append(owner)
            continue
        if len(raw)>64*1048576:
            owner_elf[owner]={"status":"elf_too_large"}
            continue
        interesting={name for name,r in rows.items() if owner in r["owners"]}
        try:
            exported,crcs,weak,symtab=decoder.exports_from_elf(raw,interesting)
            owner_elf[owner]={"status":"parsed",
                               "export_names":set(exported),
                               "export_crcs":crcs,
                               "weak_strings_only_count":len(weak),
                               "has_symtab":symtab}
        except (ValueError,IndexError,UnicodeError,OverflowError) as e:
            owner_elf[owner]={"status":"invalid_elf_export_tables"}
    counts,owner_counts,records=classify(rows,loaded,owner_elf)
    result={
      "status":"PRIVATE CANDIDATE DISK-ELF CRC CORROBORATION, NOT LIVE KERNEL EXPORT ABI",
      "time_utc":datetime.now(timezone.utc).isoformat(),
      "triage_source_names":len(rows),
      "live_target_owner_modules":len(target_owners&loaded),
      "owner_tags_no_longer_loaded":sorted(target_owners-loaded),
      "target_owner_module_count":len(target_owners),
      "on_disk_owner_module_elves_parsed":sum(v["status"]=="parsed" for v in owner_elf.values()),
      "on_disk_owner_module_unavailable_or_invalid":sum(v["status"]!="parsed" for v in owner_elf.values()),
      "owners_without_disk_module_path":sorted(target_owners&loaded-set(owner_elf)),
      "root_enumeration_status":root_status,
      "symbol_classification_counts":counts,
      "owner_check_counts":owner_counts,
      "critical_ar9271_exports":{
        name:{"live_ksymtab_visible":bool(triage.get("critical_two_ar9271_exports",{}).get(name,{}).get("ksymtab_name_visible")),
              "actual_live_export_crc_verified":False} for name in BLOCKERS
      },
      "symbols":records,
      "warnings":[
        "A live owner tag identifies a loaded module as a possible export owner, not its CRC.",
        "A matching disk ELF export CRC is corroborating evidence, never proof of the active binary's live CRC.",
        "Do not assume any of the 264 module-provided names should be appended to vmlinux's KMI whitelist.",
        "The original Motorola KMI whitelist, module signing, CFI, exact kernelrelease and full vendor compatibility remain unverified.",
        "This analysis never insmods, flashes, modifies system, changes SELinux, installs modules or uploads private files."
      ],
    }
    os.umask(0o077)
    a.report.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(a.report,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),"w") as fp:
        json.dump(result,fp,indent=2)
        fp.write("\n")
    os.chmod(a.report,0o600)
    print("===== NEVADA PRIVATE 264 LIVE OWNER -> ON-DISK ELF/CRC GATE =====")
    print("Live owner-tagged names:",len(rows))
    print("Distinct live owner modules:",len(target_owners&loaded))
    print("Owner .ko ELFs parsed:",result["on_disk_owner_module_elves_parsed"])
    print("Loaded owners lacking .ko paths:",len(result["owners_without_disk_module_path"]))
    print("Owner candidate checks:",owner_counts)
    for status,count in counts.items():
        print(" ",status+":",count)
    for sym in BLOCKERS:
        print("Critical "+sym+": live_ksymtab_visible="+str(result["critical_ar9271_exports"][sym]["live_ksymtab_visible"]))
    print("Private results:",a.report)
    print("Any matching ELF CRC is NOT a live export CRC. NO FLASH/INSMOD.")

if __name__=="__main__":
    main()
