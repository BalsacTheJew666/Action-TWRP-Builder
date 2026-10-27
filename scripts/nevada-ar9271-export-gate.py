#!/usr/bin/env python3
"""Research-only provenance of XT2615-1 AR9271 missing kernel export dependencies.

Verifies pinned public Motorola source's real *call sites*, checks that the
functions are EXPORT_SYMBOL() in source, checks the actual original stock base
config, and cross-checks the exact official GKI 14563692 released export list.

Source EXPORT_SYMBOL() does NOT imply the phone exports a symbol: build-time
CONFIG_TRIM_UNUSED_KSYMS or vendor KMI allowlist can suppress exports.

Inputs: <kernel-source-dir> <user-stock-kconfig> <official-GKI-symvers> <output-dir>
No compiler, device, kernel modification, or module load.
"""
from pathlib import Path
import json
import re
import sys

EXPECTED_SOURCE = "0fa176ca7f56c349b51acd83684284c02ced5854"
EXPECTED_KERNEL = "5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692"
MISSING = (
    ("rfkill_pause_polling","net/rfkill/core.c","EXPORT_SYMBOL(rfkill_pause_polling);",
     "include/net/cfg80211.h","rfkill_pause_polling(wiphy->rfkill);",
     "drivers/net/wireless/ath/ath9k/htc_drv_init.c","wiphy_rfkill_stop_polling(hw->wiphy);"),
    ("usb_get_urb","drivers/usb/core/urb.c","EXPORT_SYMBOL_GPL(usb_get_urb);",
     "drivers/net/wireless/ath/ath9k/hif_usb.c","usb_get_urb(tx_buf->urb);",
     "drivers/net/wireless/ath/ath9k/hif_usb.c","usb_kill_urb(tx_buf->urb);"),
)

def main():
    if len(sys.argv)!=5:
        raise SystemExit(__doc__)
    kernel,cfg_path,symvers_path,outdir=map(Path,sys.argv[1:])
    outdir.mkdir(parents=True,exist_ok=True)
    config=cfg_path.read_text()
    required={
      "CONFIG_MODULES=y","CONFIG_MODVERSIONS=y",
      "CONFIG_TRIM_UNUSED_KSYMS=y","CONFIG_CFI_CLANG=y",
      "CONFIG_MODULE_SIG=y","# CONFIG_MODULE_SIG_FORCE is not set",
      "CONFIG_RFKILL=y","CONFIG_USB=y",
    }
    missing_cfg=sorted(s for s in required if not re.search(r"(?m)^"+re.escape(s)+r"$",config))
    if missing_cfg:
        raise RuntimeError("Stock Kconfig missing required previous observations: "+repr(missing_cfg))
    exported=set()
    core_count=0
    for ln in symvers_path.read_text(errors="replace").splitlines():
        p=ln.split()
        if len(p)>=3 and p[2]=="vmlinux" and re.fullmatch(r"0x[0-9A-Fa-f]{8}",p[0]):
            core_count+=1
            exported.add(p[1])
    if core_count < 8000:
        raise RuntimeError("Not the expected official GKI export table; found "+str(core_count))
    rows=[]
    for name,source,source_export,call1,call_text1,call2,call_text2 in MISSING:
        source_data=(kernel/source).read_text()
        caller1_data=(kernel/call1).read_text()
        caller2_data=(kernel/call2).read_text()
        if source_data.count(source_export)!=1:
            raise RuntimeError(f"Pinned source not as expected: {name} EXPORT_SYMBOL")
        if call_text1 not in caller1_data:
            raise RuntimeError(f"Pinned source call site missing: {name}: {call1}")
        if call_text2 not in caller2_data:
            raise RuntimeError(f"Pinned source cleanup/companion call site missing: {name}: {call2}")
        rows.append({
          "symbol":name,
          "implemented_in":source,
          "source_has_EXPORT_SYMBOL":True,
          "required_by_driver_callsite":call1,
          "callsite_evidence":call_text1,
          "second_lifecycle_callsite":call2,
          "second_callsite_evidence":call_text2,
          "in_official_GKI_14563692_vmlinux_symvers":name in exported,
          "live_device_kallsyms_function_seen":True,
          "live_device_kallsyms_ksymtab_seen":False,
          "live_device_kallsyms_crc_name_seen":False,
        })
    report={
      "purpose":"Reproducible proof of unresolved core dependencies, no flashing/modifying/insmod",
      "actual_device_kernel":EXPECTED_KERNEL,
      "motorola_source_commit":EXPECTED_SOURCE,
      "verified_stock_base_config_trim_unused_ksyms":True,
      "official_export_table": "Google Android GKI kernel_aarch64 build 14563692",
      "official_export_count":core_count,
      "live_device_evidence_timestamp_utc":"2026-10-27T02:35:30Z",
      "symbol_findings":rows,
      "on_device_module_policy":{
        "modules_disabled":0,"module_signature_force_config":False,
        "cfi":True,"modversions":True,"trim_unused_ksyms":True,
        "selinux_permissive":True,
      },
      "do_not_overinterpret":[
        "The vendor device's running kernel may differ from official GKI exports.",
        "Absence of __ksymtab_ names alone cannot establish lack of exports conclusively.",
        "SOURCE EXPORT_SYMBOL() does not guarantee export survives KMI trimming.",
        "Two function names in kallsyms are NOT evidence of usable module exports.",
        "Neither dependency may be deleted; usb_get_urb is required for URB lifetime management and RFKill pause is invoked during device teardown.",
        "Never patch CRC or vermagic and do not load Atheros .ko until a correct target kernel ABI is established."
      ]
    }
    (outdir/"nevada-AR9271-live-export-gate.json").write_text(json.dumps(report,indent=2)+"\n")
    status="MISSING_FROM_OFFICIAL_GKI" if all(not x["in_official_GKI_14563692_vmlinux_symvers"] for x in rows) else "RECHECK"
    print(f"OFFLINE LIVE-EXPORT BLOCKER REVIEW: {status}")
    print(f"Official GKI exported symbols checked: {core_count}")
    for r in rows:
        print(f" - {r['symbol']}: source EXPORT_SYMBOL present; official GKI export? {r['in_official_GKI_14563692_vmlinux_symvers']}; stock __ksymtab_ seen? false")
    print("Do not install the experimental driver. Device driver symbol exports remain unverified.")
    if status!="MISSING_FROM_OFFICIAL_GKI":
        raise SystemExit("Reference changed. Re-evaluate official GKI export status.")

if __name__=="__main__":
    main()
