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


    # Android aliases often expose the same .ko bytes at different paths.
    # The old script skipped every duplicated name and read ZERO modules.
    alias_dir=modules/"alias"
    alias_dir.mkdir()
    original_bytes=(modules/"example.ko").read_bytes()
    (alias_dir/"example.ko").write_bytes(original_bytes)
    aliased_report=root/"aliased-report.json"
    aliased=subprocess.run([
        sys.executable,str(WITNESS),"--manifest",str(MANIFEST),
        "--offline-dir",str(modules),"--output",str(aliased_report)],
        check=False,capture_output=True,text=True,timeout=20
    )
    assert aliased.returncode==0,aliased.stderr
    alias_data=json.loads(aliased_report.read_text())
    assert alias_data["loaded_module_names"]==1,alias_data
    assert alias_data["module_ELFs_read"]==1,alias_data
    assert alias_data["matching_symbol_witnesses"]==1,alias_data
    assert alias_data["identical_duplicate_groups_resolved"]==1,alias_data
    print("PASS: duplicate mounted .ko filenames with identical bytes produce a witness")

    # Two DIFFERENT binaries under the same module name must NOT be silently
    # selected when no running module Build-ID establishes identity.
    distinct=bytearray(original_bytes)
    distinct[-1]^=1
    (alias_dir/"example.ko").write_bytes(distinct)
    conflicting_report=root/"conflicting-report.json"
    conflicting=subprocess.run([
        sys.executable,str(WITNESS),"--manifest",str(MANIFEST),
        "--offline-dir",str(modules),"--output",str(conflicting_report)],
        check=False,capture_output=True,text=True,timeout=20
    )
    assert conflicting.returncode==0,conflicting.stderr
    conflict_data=json.loads(conflicting_report.read_text())
    assert conflict_data["module_ELFs_read"]==0,conflict_data
    assert conflict_data["matching_symbol_witnesses"]==0,conflict_data
    assert conflict_data["ambiguous_module_names"]==["example"],conflict_data
    assert conflict_data["module_selection_reasons"]["different_content_candidates"]==1
    print("PASS: distinct binary candidates remain unresolved, never arbitrarily chosen")

    # Root-visible running module Build-ID can resolve distinct copies,
    # without reading kernel pointers or guessing from module path order.
    import struct as _struct
    def build_id_elf(marker):
        shstr=b'\0.shstrtab\0.note.gnu.build-id\0'
        note=_struct.pack('<III',4,20,3)+b'GNU\0'+bytes([marker])*20
        obj=bytearray(640)
        obj[:16]=b'\x7fELF\x02\x01\x01'+bytes(9)
        shoff=384
        _struct.pack_into('<HHIQQQIHHHHHH',obj,16,
                          1,183,1,0,0,shoff,0,64,0,0,64,3,1)
        obj[64:64+len(shstr)]=shstr
        obj[160:160+len(note)]=note
        fmt='<IIQQQQIIQQ'
        _struct.pack_into(fmt,obj,shoff+64,1,3,0,0,64,len(shstr),0,0,1,0)
        _struct.pack_into(fmt,obj,shoff+128,11,7,0,0,160,len(note),0,0,4,0)
        return bytes(obj),note
    newer,note_new=build_id_elf(7)
    older,note_old=build_id_elf(9)
    read_map={
      '/tmp/one/example.ko':newer,
      '/tmp/two/example.ko':older,
      '/sys/module/example/notes/.note.gnu.build-id':note_new,
    }
    with mock.patch.object(witness,"read",side_effect=lambda p:read_map.get(str(p))):
        selected,reason,unique,unreadable=witness.resolve_candidate(
            "example",[Path('/tmp/one/example.ko'),Path('/tmp/two/example.ko')],
            "normal_boot")
        assert selected==newer and reason=="build_id_verified_unique"
        assert unique==2 and unreadable==0
        print("PASS: exact live module GNU Build-ID selects correct candidate")
        read_map['/sys/module/example/notes/.note.gnu.build-id']=b'other'
        selected,reason,unique,unreadable=witness.resolve_candidate(
            "example",[Path('/tmp/one/example.ko'),Path('/tmp/two/example.ko')],
            "normal_boot")
        assert selected is None and reason=="live_build_id_not_matched"
        print("PASS: build-ID mismatch rejects both candidates safely")
