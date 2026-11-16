#!/usr/bin/env python3
"""End-to-end synthetic test of private __ksymtab owner-tag attribution.

No device, su, proprietary binary, firmware, or kernel pointer is read.
"""
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PROGRAM=ROOT/"scripts/nevada-vendor-live-ksymtab-owner-witness.py"

with tempfile.TemporaryDirectory(prefix="nv-owner-fixture-") as tmp:
    base=Path(tmp)
    report=base/"provider-report.json"
    report.write_text(json.dumps({
      "source_stock_inventory_name_count":1119,
      "live_ksymtab_name_unattributed":["alpha","beta","gamma","delta","epsilon"],
    }))
    ksym=base/"kallsyms.txt"
    ksym.write_text("""0000000000000000 r __ksymtab_alpha
0000000000000000 r __ksymtab_beta [wifi_mod]
0000000000000000 r __ksymtab_gamma [not_loaded]
0000000000000000 r __ksymtab_delta [wifi_mod]
0000000000000000 r __ksymtab_delta
0000000000000000 r unrelated_function
0000000000000000 r __ksymtab_rfkill_pause_polling [wifi_mod]
""")
    modules=base/"modules.txt"
    modules.write_text("wifi_mod 130000 0 - Live 0x00000000\n")
    output=base/"owner.json"
    result=subprocess.run([
      sys.executable,str(PROGRAM),
      "--provider-report",str(report),"--output",str(output),
      "--kallsyms-file",str(ksym),"--modules-file",str(modules)],
      capture_output=True,text=True,timeout=15)
    if result.returncode:
        raise SystemExit(result.stdout+"\n"+result.stderr)
    doc=json.loads(output.read_text())
    count=doc["owner_classification_counts"]
    assert count=={
      "ambiguous_or_unrecognized_owner":2,
      "explicit_loaded_module_owner":1,
      "no_longer_seen_in_kallsyms":1,
      "untagged_export_owner_not_proven":1,
    },count
    classified=doc["symbol_name_owner_witnesses"]
    assert classified["alpha"]["classification"]=="untagged_export_owner_not_proven"
    assert classified["beta"]["explicit_live_module_owner_tags"]==["wifi_mod"]
    assert classified["delta"]["classification"]=="ambiguous_or_unrecognized_owner"
    assert classified["epsilon"]["classification"]=="no_longer_seen_in_kallsyms"
    assert doc["critical_ar9271_exports"]["rfkill_pause_polling"]["ksymtab_name_seen"]
    assert not doc["critical_ar9271_exports"]["usb_get_urb"]["ksymtab_name_seen"]
    assert not classified["alpha"]["live_vmlinux_export_proven"]
    assert not classified["beta"]["export_crc_proven"]
    assert (output.stat().st_mode&0o777)==0o600
    assert "0000000000000000" not in output.read_text()
    print("PASS: full command and offline synthetic ksymtab owner-tag classification")
    print("PASS: does not mistake untagged entries for proven live vmlinux exports")
    print("PASS: no kernel addresses or proprietary module bytes in local JSON")
    print("PASS: private JSON mode 0600; no root, no flash, no module load")
