#!/usr/bin/env python3
"""Read-only on-device classification of the 264 unresolved vendor ABI imports.

Takes the PRIVATE result of nevada-vendor-export-provider-local.py, which
found 742 possible already-loaded ELF module providers and 264 import names
not accounted for by readable module ELF export tables.

Cross-checks the remaining 264 *names only* with live /proc/kallsyms ksymtab
owner labels, never addresses or symbol values. A name hit does not prove
core ownership, CRC, complete Motorola KMI, or installability.

Output: owner-readable (0600) local JSON under Termux. No upload, kernel
write, root/SELinux change, insmod, flashing, or driver installation.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

EXPECTED_UNRESOLVED=264
EXPECTED_TOTAL=1006
EXPECTED_PROVIDED=742
TARGETS=("usb_get_urb","rfkill_pause_polling")
IDENT=re.compile(r"^[a-zA-Z_][a-zA-Z_0-9]*$")
MODTAG=re.compile(r"^\[([A-Za-z0-9_\-]+)\]$")

def read_readonly(path):
    try:
        return Path(path).read_bytes()
    except OSError:
        p=subprocess.run(["su","-c","cat "+shlex.quote(str(path))],
                         capture_output=True,timeout=60,check=False)
        if p.returncode:
            raise RuntimeError("Root-assisted read failed: "+str(path))
        return p.stdout

def read_candidate_names(path):
    data=json.loads(path.read_text())
    if data.get("mode")!="normal_boot_private_device":
        raise ValueError("Only user-controlled normal-boot private report is accepted")
    buckets=data.get("result_buckets",{})
    if (data.get("public_GKI_absent_imported_names_examined")!=EXPECTED_TOTAL
        or buckets.get("no_provider_seen_among_readable_loaded_modules")!=EXPECTED_UNRESOLVED
        or buckets.get("one_loaded_module_ELF_declaration")!=EXPECTED_PROVIDED):
        raise ValueError("Unexpected or incomplete initial 742/264 stock module provider analysis")
    records=data.get("provider_candidates")
    if not isinstance(records,dict) or len(records)!=EXPECTED_TOTAL:
        raise ValueError("Invalid provider candidate records")
    unresolved={name for name,row in records.items()
                if row.get("classification")=="no_provider_seen_among_readable_loaded_modules"}
    if len(unresolved)!=EXPECTED_UNRESOLVED or not all(IDENT.fullmatch(x) for x in unresolved):
        raise ValueError("Unexpected unresolved symbol name count/format")
    return unresolved

def extract_modules(blob):
    result=set()
    for line in blob.splitlines():
        parts=line.split()
        if not parts:
            continue
        name=parts[0].decode("ascii","replace").replace("-","_")
        if IDENT.fullmatch(name):
            result.add(name)
    return result

def extract_export_names(blob,wanted):
    owners=defaultdict(set)
    total_export_entries=0
    for line in blob.splitlines():
        parts=line.split()
        if len(parts)<3:
            continue
        value=parts[2].decode("ascii","replace")
        if not value.startswith("__ksymtab_"):
            continue
        total_export_entries+=1
        name=value[len("__ksymtab_"):]
        if name not in wanted:
            continue
        owner="UNTAGGED"
        if len(parts)>=4:
            m=MODTAG.fullmatch(parts[-1].decode("ascii","replace"))
            if m:
                owner=m.group(1).replace("-","_")
        owners[name].add(owner)
    return owners,total_export_entries

def classify(wanted,owners,loaded):
    findings={}
    counts=Counter()
    for name in sorted(wanted):
        observed=owners.get(name,set())
        tagged_loaded=sorted(x for x in observed if x!="UNTAGGED" and x in loaded)
        other_tags=sorted(x for x in observed if x!="UNTAGGED" and x not in loaded)
        untagged="UNTAGGED" in observed
        if not observed:
            status="no_visible_ksymtab_name"
        elif tagged_loaded and not other_tags and not untagged:
            status="live_loaded_module_owner_tag"
        elif untagged and not tagged_loaded and not other_tags:
            status="visible_untagged_export_owner_unknown"
        else:
            status="multiple_or_unrecognized_owner_tags"
        findings[name]={
            "status":status,
            "loaded_module_owner_tags":tagged_loaded,
            "other_owner_tags":other_tags,
            "untagged_ksymtab_seen":untagged,
            "core_vmlinux_export_proven":False,
            "export_crc_proven":False
        }
        counts[status]+=1
    return findings,dict(sorted(counts.items()))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--provider-report",type=Path,required=True)
    p.add_argument("--report",type=Path,required=True)
    p.add_argument("--kallsyms-file",type=Path,
                   help="Synthetic fixture only (CI); default is live /proc/kallsyms")
    p.add_argument("--modules-file",type=Path,
                   help="Synthetic fixture only (CI); default is live /proc/modules")
    args=p.parse_args()

    if args.report.resolve()==args.provider_report.resolve():
        raise SystemExit("Refusing to overwrite original private report")
    unresolved=read_candidate_names(args.provider_report)
    ksym_blob=read_readonly(args.kallsyms_file or "/proc/kallsyms")
    modules_blob=read_readonly(args.modules_file or "/proc/modules")
    wanted=unresolved|set(TARGETS)
    owners,total=extract_export_names(ksym_blob,wanted)
    loaded=extract_modules(modules_blob)
    findings,counts=classify(unresolved,owners,loaded)
    blocker_info={}
    for name in TARGETS:
        existing=owners.get(name,set())
        blocker_info[name]={
          "ksymtab_name_visible":bool(existing),
          "loaded_module_owner_tags":sorted(x for x in existing if x!="UNTAGGED" and x in loaded),
          "untagged_name_visible":"UNTAGGED" in existing,
          "actual_module_export_crc_verified":False,
        }
    report={
       "status":"PRIVATE NAME-ONLY EXPORT VISIBILITY TRIAGE; NOT CORE KMI PROOF",
       "timestamp_utc":datetime.now(timezone.utc).isoformat(),
       "source_private_provider_count":EXPECTED_PROVIDED,
       "original_private_import_names":EXPECTED_TOTAL,
       "unresolved_names_checked":len(unresolved),
       "readable_live_module_names":len(loaded),
       "total_ksymtab_export_entries_seen":total,
       "visible_export_table_entries":total>0,
       "classification_counts":counts,
       "unresolved_name_details":findings,
       "critical_two_ar9271_exports":blocker_info,
       "limitations":[
           "An untagged ksymtab name does not prove vmlinux ownership.",
           "A tagged owner name does not prove module CRC or exact loaded binary version.",
           "Missing names do not establish missing exports; kallsyms and loaded module coverage can be incomplete.",
           "Missing 177 readable stock ELF files may conceal other providers; never append the 264 names wholesale to vmlinux's ABI whitelist.",
           "No kernel changes, insmod, forced loading or device flashing; no NetHunter installation authorization.",
       ]
    }
    os.umask(0o077)
    args.report.parent.mkdir(parents=True,exist_ok=True)
    with os.fdopen(os.open(args.report,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),
                   "w",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
        f.write("\n")
    os.chmod(args.report,0o600)
    print("===== MOTOROLA NEVADA 264 UNRESOLVED LIVE EXPORT-NAME TRIAGE =====")
    print("Names checked:",len(unresolved))
    print("Live ksymtab export entries visible:",total)
    for status,n in sorted(counts.items()):
        print(f"  {status}: {n}")
    for name in TARGETS:
        print(f"Critical {name}: ksymtab_name_visible={blocker_info[name]['ksymtab_name_visible']}")
    print("Detailed report remains private in Termux:",args.report)
    print("Name visibility is NOT live kernel CRC evidence. NO FLASH/INSMOD.")

if __name__=="__main__":
    main()
