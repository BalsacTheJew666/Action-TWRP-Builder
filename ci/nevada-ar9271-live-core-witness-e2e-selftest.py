#!/usr/bin/env python3
"""Execute complete read-only witness collection with synthetic ELF and 101-symbol manifest.

The earlier CI only py_compiled the source and exercised imports(...), missing
a runtime UnboundLocalError when report was mutated before assignment.
"""
import json
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

REPO=Path(__file__).resolve().parents[1]
WITNESS=REPO/"scripts/nevada-ar9271-live-core-kmi-witness.py"
MANIFEST=REPO/"ci/nevada-ar9271-core-kmi.tsv"

def synthetic_elf():
    shstr=b"\0.shstrtab\0__versions\0"
    record=struct.pack("<Q",0x61a2317d)+b"usb_submit_urb\0".ljust(56,b"\0")
    obj=bytearray(512)
    obj[:16]=b"\x7fELF\x02\x01\x01"+bytes(9)
    shoff=320
    struct.pack_into("<HHIQQQIHHHHHH",obj,16,1,183,1,0,0,shoff,0,64,0,0,64,3,1)
    obj[64:64+len(shstr)]=shstr
    obj[112:176]=record
    header="<IIQQQQIIQQ"
    struct.pack_into(header,obj,shoff+64,1,3,0,0,64,len(shstr),0,0,1,0)
    struct.pack_into(header,obj,shoff+128,11,1,0,0,112,64,0,0,8,64)
    return bytes(obj)

with tempfile.TemporaryDirectory(prefix="nevada-witness-selftest-") as temp:
    root=Path(temp)
    modules=root/"stock-modules"
    modules.mkdir()
    (modules/"example.ko").write_bytes(synthetic_elf())
    report=root/"report.json"
    result=subprocess.run([
        sys.executable,str(WITNESS),"--manifest",str(MANIFEST),
        "--offline-dir",str(modules),"--output",str(report)],
        check=False,capture_output=True,text=True,timeout=20
    )
    print(result.stdout)
    if result.returncode:
        raise SystemExit("Witness end-to-end offline test failed:\n"+result.stderr)
    data=json.loads(report.read_text())
    assert data["mode"]=="offline_recovery_fixture"
    assert data["matching_symbol_witnesses"]==1
    assert data["matching_import_witness_entries"]==1
    assert data["conflicting_symbol_witnesses"]==0
    assert data["required_unique_core_symbols"]==101
    assert data["module_ELFs_read"]==1
    assert data["core_export_name_visibility"]=={
        "rfkill_pause_polling":"unavailable",
        "usb_get_urb":"unavailable",
        "kallsyms_exports_visible":False
    },data["core_export_name_visibility"]
    print("PASS: end-to-end report creation, runtime field initialization and import CRC classification")

    # Unit-test root-only *path enumeration* without ever invoking su or
    # scanning the runner's real filesystem. Termux has a mount namespace in
    # which os.walk can return no paths, so a root find fallback is needed.
    import importlib.util
    from unittest import mock
    spec=importlib.util.spec_from_file_location("nevada_witness",WITNESS)
    witness=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(witness)
    with mock.patch.object(witness.subprocess,"run") as execute:
        execute.return_value=subprocess.CompletedProcess(
            args=["su","-c","find"],returncode=0,
            stdout=(str(modules/"example.ko")+"\n").encode(),stderr=b""
        )
        files,root_status=witness.scan_as_root(
            ["/vendor_dlkm/lib/modules"],{"example"}
        )
        assert files["example"]==[modules/"example.ko"],files
        assert root_status["status"]=="ok"
        assert root_status["root_loaded_name_matches"]==1
        assert execute.call_args.args[0][:2]==["su","-c"]
        shell=execute.call_args.args[0][2]
        assert "find" in shell and "insmod" not in shell
        print("PASS: mock rooted read-only path scan discovers inaccessible stock module")

    with mock.patch.object(witness.subprocess,"run") as execute:
        execute.side_effect=FileNotFoundError("su unavailable")
        files,root_status=witness.scan_as_root(
            ["/vendor_dlkm/lib/modules"],{"example"}
        )
        assert not files and root_status["status"]=="FileNotFoundError"
        print("PASS: missing root access is labeled as unavailable, not a CRC mismatch")

