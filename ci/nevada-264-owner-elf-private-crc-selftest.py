#!/usr/bin/env python3
"""Synthetic-only regression for private 264 live-owner candidate ELF CRC gate.

There are NO phone files or proprietary module blobs in this test.
"""
import importlib.util
from pathlib import Path
import tempfile
import json

ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/"scripts/nevada-264-owner-elf-private-crc-gate.py"
spec=importlib.util.spec_from_file_location("nv264owner",SRC)
audit=importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)

triage={
  "unresolved_names_checked":264,
  "classification_counts":{"live_loaded_module_owner_tag":264},
  "unresolved_name_details":{},
  "critical_two_ar9271_exports":{
    "usb_get_urb":{"ksymtab_name_visible":False},
    "rfkill_pause_polling":{"ksymtab_name_visible":False}
  }
}
provider={"provider_candidates":{}}
rows={}
for i in range(264):
    sym=f"example_symbol_{i:03d}"
    owner=f"provider_{i//66}"
    crc=0x12000000+i
    triage["unresolved_name_details"][sym]={
      "status":"live_loaded_module_owner_tag",
      "loaded_module_owner_tags":[owner]
    }
    provider["provider_candidates"][sym]={
      "classification":"no_provider_seen_among_readable_loaded_modules",
      "imported_crc_requirements":[f"0x{crc:08x}"]
    }
    rows[sym]={"owners":[owner],"required":{crc}}
for i in range(742):
    provider["provider_candidates"][f"elsewhere_{i:04d}"]={"classification":"one_loaded_module_ELF_declaration"}
assert audit.inputs(triage,provider)==rows
print("PASS: genuine private-report schema test with 264 owner-tag records and 1006 provider entries")

owners={
    "provider_0":{"status":"parsed","export_names":{f"example_symbol_{i:03d}" for i in range(66)},
                  "export_crcs":{f"example_symbol_{i:03d}":0x12000000+i for i in range(66)}},
    "provider_1":{"status":"parsed","export_names":{f"example_symbol_{i:03d}" for i in range(66,132)},
                  "export_crcs":{}},
    "provider_2":{"status":"parsed","export_names":{f"example_symbol_{i:03d}" for i in range(132,198)},
                  "export_crcs":{f"example_symbol_{i:03d}":0x1 for i in range(132,198)}},
}
counts,owner_checks,detail=audit.classify(rows,set(owners)|{"provider_3"},owners)
expected={
   "all_owner_candidate_elf_crcs_match_imports":66,
   "elf_declared_export_without_crc":66,
   "candidate_elf_crc_conflict_needs_manual_review":66,
   "owner_tag_only_or_disk_elf_missing":66,
}
assert counts==expected,(counts,expected)
assert owner_checks["candidate_elf_crc_matches_import"]==66
assert owner_checks["candidate_elf_crc_conflicts_with_import"]==66
assert owner_checks["elf_export_abs_crc_not_present"]==66
assert owner_checks["no_matching_on_disk_elf"]==66
assert all(not x["live_core_export_crc_verified"] for x in detail.values())
print("PASS: exact CRC matching, conflict flags, missing source, and unverified-vmlinux flags")

bad=json.loads(json.dumps(triage))
bad["unresolved_name_details"]["example_symbol_000"]["loaded_module_owner_tags"]=[]
try:
    audit.inputs(bad,provider)
except ValueError:
    print("PASS: missing owner tag rejected")
else:
    raise SystemExit("Invalid owner tag unexpectedly accepted")

print("PASS: synthetic-only selftest; no device access or private vendor files")
