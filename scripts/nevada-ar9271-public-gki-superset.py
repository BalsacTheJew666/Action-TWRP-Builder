#!/usr/bin/env python3
"""Build a research-only PUBLIC-GKI export superset, never a Motorola stock KMI file.

Inputs:
 - Official public Google GKI kernel_aarch64 build 14563692 vmlinux.symvers.
 - Sanitized 101 unique AR9271 experimental core-import CRC requirements.
 - Directory for text-only proof artifacts.

This is a conservative PUBLIC baseline containing every official GKI vmlinux
export plus two missing Atheros dependencies. It CANNOT reconstruct extra
Motorola vendor-specific exports, nor recover the proprietary original
abi_symbollist.raw, nor establish module loadability or boot safety.
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import re
import sys

OFFICIAL_GKI_BUILD="14563692"
BASE_KERNEL_RELEASE="5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692"
BASE_GKI_SHA="9b2308ac0ad616788fb57ba688aa07f0ff221355"
NEEDED_ADDITIONS={"rfkill_pause_polling","usb_get_urb"}
MIN_GKI_EXPORTS=8400
MAX_GKI_EXPORTS=8600
EXPECTED_REQUIREMENTS=101

def read_symvers(path):
    symbols={}
    provider_counts=Counter()
    rows=0
    for lineno,line in enumerate(path.read_text().splitlines(),1):
        parts=line.split()
        if not parts:
            continue
        if len(parts)<4 or not re.fullmatch(r"0x[0-9a-fA-F]{8}",parts[0]):
            raise RuntimeError(f"Not a genuine Module.symvers row: line {lineno}")
        crc=int(parts[0],16)
        name,owner=parts[1:3]
        provider_counts[owner]+=1
        if owner!="vmlinux":
            continue
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*",name):
            raise RuntimeError(f"Unexpected symbol name {name!r}")
        if name in symbols and symbols[name]!=crc:
            raise RuntimeError(f"Conflicting official CRC for {name}")
        symbols[name]=crc
        rows+=1
    if not MIN_GKI_EXPORTS<=len(symbols)<=MAX_GKI_EXPORTS:
        raise RuntimeError(f"Official GKI export count {len(symbols)} outside expected verified range")
    return symbols,provider_counts,rows

def read_requirements(path):
    with path.open(newline="") as f:
        data=list(csv.DictReader(f,delimiter="\t"))
    if len(data)!=EXPECTED_REQUIREMENTS or len({row.get("symbol") for row in data})!=len(data):
        raise RuntimeError("The pinned AR9271 101-symbol requirement file changed")
    out={}
    for row in data:
        if set(row)!={"symbol","crc"}:
            raise RuntimeError("Unexpected 101-symbol TSV format")
        if not re.fullmatch(r"0x[0-9a-fA-F]{8}",row["crc"]):
            raise RuntimeError(f"Bad requirement CRC for {row['symbol']}")
        out[row["symbol"]]=int(row["crc"],16)
    if not NEEDED_ADDITIONS<=set(out):
        raise RuntimeError("Two known missing AR9271 symbols absent from requirements")
    return out

def main():
    if len(sys.argv)!=4:
        raise SystemExit(__doc__)
    official_path,requirements_path,output_dir=map(Path,sys.argv[1:])
    output_dir.mkdir(parents=True,exist_ok=True)
    official,providers,rows=read_symvers(official_path)
    requirements=read_requirements(requirements_path)
    existing_targets=NEEDED_ADDITIONS&set(official)
    if existing_targets:
        raise RuntimeError(f"Official GKI unexpectedly exports missing symbols: {sorted(existing_targets)}")
    comparisons={}
    for name,needed_crc in sorted(requirements.items()):
        observed=official.get(name)
        status=("not_in_official_gki" if observed is None else
                "official_crc_match" if observed==needed_crc else "official_crc_conflict")
        comparisons[name]={
            "required_import_crc":f"0x{needed_crc:08x}",
            "official_gki_export_crc":None if observed is None else f"0x{observed:08x}",
            "status":status,
        }
    stats=Counter(d["status"] for d in comparisons.values())
    if stats["official_crc_conflict"]:
        raise RuntimeError(f"Official GKI has {stats['official_crc_conflict']} core CRC conflicts")
    if set(name for name,datum in comparisons.items() if datum["status"]=="not_in_official_gki")!=NEEDED_ADDITIONS:
        raise RuntimeError("The 101-symbol candidate-vs-official reference gaps changed unexpectedly")

    superset=sorted(set(official)|NEEDED_ADDITIONS)
    assert len(superset)==len(official)+2
    out_list=output_dir/"PUBLIC-GKI-ALL-EXPORTS-PLUS-TWO-NOT-VENDOR-COMPLETE.symbollist"
    out_list.write_text("\n".join(superset)+"\n")
    if out_list.stat().st_size<100000:
        raise RuntimeError("Refusing unexpectedly small KMI superset file")
    digest=hashlib.sha256(out_list.read_bytes()).hexdigest()
    manifest={
        "classification":"PUBLIC-GKI SUPERSET ONLY; NOT COMPLETE ORIGINAL MOTOROLA KMI WHITELIST",
        "official_gki_build":OFFICIAL_GKI_BUILD,
        "matching_live_phone_kernel_release":BASE_KERNEL_RELEASE,
        "base_gki_source_sha":BASE_GKI_SHA,
        "official_input_file_sha256":hashlib.sha256(official_path.read_bytes()).hexdigest(),
        "source_requirement_manifest_sha256":hashlib.sha256(requirements_path.read_bytes()).hexdigest(),
        "generated_superset_sha256":digest,
        "official_gki_unique_vmlinux_exports":len(official),
        "superset_export_symbol_names":len(superset),
        "added_symbols":sorted(NEEDED_ADDITIONS),
        "ath9k_core_import_unique_symbols":len(requirements),
        "ath9k_core_import_result_counts":dict(stats),
        "ath9k_core_import_comparison":comparisons,
        "verified_device_stock_module_witnesses":"82/101 with zero observed conflicts, from separate read-only user-run audit",
        "important_limitations":[
            "Public GKI exported names plus two is not an authentic vendor full ABI symbol list.",
            "The missing vendor abi_symbollist.raw was private, so any additional vendor-only exports may be absent.",
            "No live GKI exported CRC is measured by generating this list; the 2 new exports have NO authoritative live CRC.",
            "This does not reproduce the exact Motorola stock ABI, kernelrelease, compiler, signature, CFI or module loader.",
            "A build using this symbol list could break Android, vendor drivers and stock Wi-Fi. Research-only; never flash."
        ]
    }
    (output_dir/"PUBLIC-GKI-SUPERSET-ABIGATE.json").write_text(json.dumps(manifest,indent=2)+"\n")
    (output_dir/"README-NEVER-FLASH.txt").write_text(
        "PUBLIC AND INCOMPLETE GKI KMI RETENTION SUPERSET, NOT THE MOTOROLA STOCK LIST.\n"
        f"Official public GKI: {len(official)} names\n"
        f"Two AR9271 additions: {', '.join(sorted(NEEDED_ADDITIONS))}\n"
        f"Combined superset: {len(superset)} names\n"
        f"AR9271 101 core-symbol import CRC matches to public official GKI: {stats['official_crc_match']}\n"
        "AR9271 core import gaps in official GKI: 2 (both present only as superset NAMES).\n"
        "Remaining vendor-only exports not proven preserved. NO KERNEL BUILD/FLASH APPROVAL.\n"
        "DO NOT USE IN A DEVICE BOOT IMAGE, INSMOD OR PATCH THE LOADER.\n"
    )
    print((output_dir/"README-NEVER-FLASH.txt").read_text())
    print(f"PUBLIC EXPORT SUPERSET CHECKSUM: {digest}")
    print(f"PASS: {stats['official_crc_match']}/101 public GKI core-symbol CRCs match; 2 not in official GKI")

if __name__=="__main__":
    main()
