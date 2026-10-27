#!/usr/bin/env python3
"""Nevada Android 16 READ-ONLY stock module import inventory.

Collect every readable stock .ko from existing dlkm/system/vendor mount trees.
Compare each module's __versions IMPORT CRCs against the exact PUBLIC GKI
14563692 vmlinux.symvers. Report the imports whose provider must be verified
elsewhere; these can belong to another .ko, vendor-built-in code, or kernel
exports unavailable in public GKI. NOT the full original Motorola ABI list.

This tool never exports/upload binary bytes, manipulates boot/system, insmods,
signs, changes SELinux or modifies device partitions. It reads .ko and a
downloaded public symbol table only. All output is local metadata.
"""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import subprocess

DIRS=(
 '/vendor_dlkm/lib/modules','/system_dlkm/lib/modules','/odm_dlkm/lib/modules',
 '/vendor/lib/modules','/system/lib/modules','/odm/lib/modules','/lib/modules'
)
GKI_BUILD="14563692"
GKI_REQUIRED_EXPORT_COUNT=8471

def load_witness():
    path=Path(__file__).with_name("nevada-ar9271-live-core-kmi-witness.py")
    if not path.is_file():
        raise SystemExit("Companion read-only witness script missing: "+str(path))
    spec=importlib.util.spec_from_file_location("nevada_kmi_witness",str(path))
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def official_core_exports(path,verify_count=True):
    result={}
    for i,line in enumerate(path.read_text().splitlines(),1):
        p=line.split()
        if not p:
            continue
        if len(p)<4 or not re.fullmatch(r"0x[0-9A-Fa-f]{8}",p[0]):
            raise ValueError(f"Official symvers malformed at line {i}")
        if p[2]!="vmlinux":
            continue
        name,crc=p[1],int(p[0],16)
        if name in result and result[name]!=crc:
            raise ValueError(f"Conflicting official GKI export {name}")
        result[name]=crc
    if verify_count and len(result)!=GKI_REQUIRED_EXPORT_COUNT:
        raise ValueError("Wrong official GKI 14563692 symbol list: "+
                         f"{len(result)} exports, expected {GKI_REQUIRED_EXPORT_COUNT}")
    return result

def paths_from_root(dirs):
    quoted=" ".join(shlex.quote(str(d)) for d in dirs)
    cmd=(
      'for d in '+quoted+'; do [ -d "$d" ] || continue; '
      '(find -L "$d" -type f -name "*.ko" -print0 2>/dev/null || '
      'find "$d" -type f -name "*.ko" -print0 2>/dev/null); done'
    )
    try:
        completed=subprocess.run(["su","-c",cmd],capture_output=True,
                                 timeout=120,check=False)
    except (OSError,subprocess.TimeoutExpired) as exc:
        return set(),{"status":type(exc).__name__,"root_found":0}
    files={os.fsdecode(p) for p in completed.stdout.split(b"\0")
           if p.startswith(b"/") and p.endswith(b".ko")}
    return files,{"status":"ok" if completed.returncode==0 else "nonzero",
                  "root_found":len(files)}

def paths_from_user(dirs):
    found=set()
    for directory in dirs:
        if not os.path.isdir(directory):
            continue
        for base,_,files in os.walk(directory):
            for name in files:
                if name.endswith(".ko"):
                    found.add(str(Path(base,name)))
    return found

def analyze(official, candidates, witness):
    groups=defaultdict(list)
    for path in sorted(candidates):
        if path.startswith("/") or not path.startswith(".."):
            name=Path(path).name
            if name.endswith(".ko"):
                groups[name[:-3].replace("-","_")].append(Path(path))
    report={"candidate_names":len(groups),"candidate_paths":len(candidates)}
    skipped=defaultdict(list)
    accepted={}
    aliases=0
    for module,paths in sorted(groups.items()):
        raw,status,collapsed=witness.select_matching_module(paths,reader=witness.read)
        aliases+=collapsed
        if raw is None:
            skipped[status].append(module)
            continue
        parsed=witness.imports(raw)
        if not parsed:
            skipped["no_valid_versions"].append(module)
            continue
        accepted[module]=parsed

    import_map=defaultdict(lambda:defaultdict(set))
    for module,versions in accepted.items():
        for symbol,crc in versions.items():
            import_map[symbol][crc].add(module)

    classes=Counter()
    imports_in_modules=Counter()
    records=[]
    for symbol,crc_modules in sorted(import_map.items()):
        gki=official.get(symbol)
        versions=[]
        for value,modules in sorted(crc_modules.items()):
            category=("not_in_public_gki" if gki is None else
                      "public_gki_crc_match" if value==gki else
                      "public_gki_crc_conflict")
            classes[category]+=1
            imports_in_modules[category]+=len(modules)
            versions.append({"import_crc":f"0x{value:08x}",
                             "category":category,
                             "importing_modules":sorted(modules)})
        records.append({
            "symbol":symbol,
            "public_gki_export_crc":None if gki is None else f"0x{gki:08x}",
            "imported_versions":versions,
            "multiple_required_crc_values":len(crc_modules)>1
        })
    report.update({
        "unique_stock_module_elfs_with_versions":len(accepted),
        "module_mount_paths_collapsed":aliases,
        "skipped_module_reasons":{k:len(v) for k,v in skipped.items()},
        "skipped_module_name_samples":{k:v[:15] for k,v in skipped.items()},
        "unique_import_names":len(import_map),
        "import_symbol_crc_pairs":sum(len(v) for v in import_map.values()),
        "crc_pair_categories":dict(classes),
        "module_import_entries_by_category":dict(imports_in_modules),
        "multiple_crc_symbols":[r["symbol"] for r in records if r["multiple_required_crc_values"]],
        "symbol_records":records,
    })
    return report

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--official-symvers",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--offline-dir",type=Path,
                    help="Synthetic fixture mode only: scan files in test directory")
    args=ap.parse_args()
    witness=load_witness()
    official=official_core_exports(args.official_symvers,
                                   verify_count=args.offline_dir is None)
    root_info={"status":"offline_fixture"}
    if args.offline_dir:
        candidates={str(x) for x in args.offline_dir.rglob("*.ko")}
        mode="offline_test_fixture"
    else:
        visible=paths_from_user(DIRS)
        rooted,root_info=paths_from_root(DIRS)
        if not rooted and not visible:
            raise SystemExit("No readable module paths; no KMI conclusion possible")
        candidates=visible|rooted
        mode="android_normal_boot_disk_modules"
    result=analyze(official,candidates,witness)
    result.update({
        "status":"READ-ONLY STOCK MODULE IMPORTS; NOT A KERNEL EXPORT CERTIFICATION",
        "mode":mode,
        "timestamp_utc":datetime.now(timezone.utc).isoformat(),
        "running_kernel":os.uname().release,
        "official_gki_build":GKI_BUILD,
        "public_gki_core_export_count":len(official),
        "root_module_path_discovery":root_info,
        "critical_limitations":[
            "Module IMPORT records are only requirements, not proof of live kernel exports.",
            "not_in_public_gki includes exports from other stock modules and vendor-built-in kernel symbols; provider must be independently established.",
            "The original private Motorola abi_symbollist.raw has not been recovered.",
            "Modules absent from these partitions cannot be assessed.",
            "No proprietary stock module bytes, phone keys, addresses or firmware are exported.",
            "Do not load AR9271, flash a custom kernel, change SELinux or bypass module signature/CFI."
        ]
    })
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(result,indent=2)+"\n")
    print("XT2615-1 NORMAL-BOOT STOCK IMPORT INVENTORY — RESEARCH ONLY")
    print("Mode:",mode,"Kernel:",os.uname().release)
    print("Official public GKI exports:",len(official))
    print("Stock module paths:",result["candidate_paths"],
          "unique modules examined:",result["unique_stock_module_elfs_with_versions"],
          "aliases collapsed:",result["module_mount_paths_collapsed"])
    print("Module discovery:",root_info,
          "skipped:",result["skipped_module_reasons"])
    print("Unique stock import symbols:",result["unique_import_names"],
          "CRC pairs:",result["import_symbol_crc_pairs"])
    print("Import CRC pair categories:",result["crc_pair_categories"])
    print("Module import entries:",result["module_import_entries_by_category"])
    missing=[r for r in result["symbol_records"]
             if any(x["category"]!="public_gki_crc_match" for x in r["imported_versions"])]
    print("Non-public-GKI or CRC-conflicted import names:",len(missing))
    print("Examples:",", ".join(x["symbol"] for x in missing[:25]))
    print("Report:",args.output)
    print("NO module was loaded or modified. This is NOT a full vendor whitelist.")
if __name__=="__main__":
    main()
