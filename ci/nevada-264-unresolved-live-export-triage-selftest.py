#!/usr/bin/env python3
"""Synthetic end-to-end regression for private 264 unresolved export-name triage.

Never reads real /proc/kallsyms, root modules or sensitive files in CI.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

REPO=Path(__file__).resolve().parents[1]
PROGRAM=REPO/"scripts/nevada-264-unresolved-live-export-triage.py"

with tempfile.TemporaryDirectory(prefix="nevada-unresolved-triage-") as temp:
    root=Path(temp)
    candidates={}
    for i in range(742):
        candidates[f"provided_{i:04d}"]={"classification":"one_loaded_module_ELF_declaration"}
    for i in range(264):
        candidates[f"unknown_{i:04d}"]={"classification":"no_provider_seen_among_readable_loaded_modules"}
    path=root/"private.json"
    path.write_text(json.dumps({
        "mode":"normal_boot_private_device",
        "public_GKI_absent_imported_names_examined":1006,
        "result_buckets":{
            "no_provider_seen_among_readable_loaded_modules":264,
            "one_loaded_module_ELF_declaration":742},
        "provider_candidates":candidates
    }))
    ksym=root/"fake-kallsyms.txt"
    ksym.write_text(
        "0000000000000000 T __ksymtab_unknown_0000 [wifi_test]\n"
        "0000000000000000 T __ksymtab_unknown_0001\n"
        "0000000000000000 T __ksymtab_unknown_0002 [not_loaded]\n"
        "0000000000000000 T __ksymtab_unknown_0003 [wifi_test]\n"
        "0000000000000000 T __ksymtab_unknown_0003\n"
        "0000000000000000 T __ksymtab_usb_get_urb\n"
        "0000000000000000 T __ksymtab_random_unrelated\n"
    )
    loaded=root/"fake-modules.txt"
    loaded.write_text("wifi_test 10240 0 - Live 0x0000000000000000\n")
    dest=root/"triage-private.json"
    result=subprocess.run([
        sys.executable,str(PROGRAM),
        "--provider-report",str(path),
        "--report",str(dest),
        "--kallsyms-file",str(ksym),
        "--modules-file",str(loaded)
    ],capture_output=True,text=True,timeout=15)
    print(result.stdout)
    if result.returncode:
        raise SystemExit(result.stderr or "Audit subprocess failed")
    data=json.loads(dest.read_text())
    assert data["unresolved_names_checked"]==264
    assert data["total_ksymtab_export_entries_seen"]==7
    assert data["classification_counts"]=={
        "live_loaded_module_owner_tag":1,
        "visible_untagged_export_owner_unknown":1,
        "multiple_or_unrecognized_owner_tags":2,
        "no_visible_ksymtab_name":260
    },data["classification_counts"]
    assert data["critical_two_ar9271_exports"]["usb_get_urb"]["ksymtab_name_visible"]
    assert not data["critical_two_ar9271_exports"]["rfkill_pause_polling"]["ksymtab_name_visible"]
    assert data["unresolved_name_details"]["unknown_0000"]["loaded_module_owner_tags"]==["wifi_test"]
    assert data["unresolved_name_details"]["unknown_0001"]["untagged_ksymtab_seen"]
    assert (dest.stat().st_mode&0o777)==0o600
    print("PASS: 264 private candidate names triaged without addresses, with synthetic loaded owner / untagged / absent classifications and 0600 local report.")
