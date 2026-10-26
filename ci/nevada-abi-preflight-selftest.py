#!/usr/bin/env python3
"""CI checks parser mechanics and preserved sanitized CRC snapshot only.

The GitHub checkout does NOT include the user's stock module ELF binaries,
so these tests do not claim to re-run the real phone module audit.
"""
import csv
import importlib.util
from pathlib import Path
import struct
from unittest.mock import patch

root = Path(__file__).resolve().parents[1]
src = root / "scripts/nevada-ar9271-stock-elf-preflight.py"
spec = importlib.util.spec_from_file_location("nevada_preflight", src)
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

# Kernel modversion entries are exactly 64 bytes: 8-byte CRC + 56-byte name.
def slot(name, crc):
    return struct.pack("<Q", crc) + name.encode()[:55].ljust(56, b"\x00")

fake = slot("ieee80211_alloc_hw_nm", 0x55EBF907) + slot("ieee80211_free_hw", 0x16785109)
with patch.object(probe, "section", return_value=fake):
    assert probe.imports(Path("/dev/null")) == {
        "ieee80211_alloc_hw_nm": 0x55EBF907,
        "ieee80211_free_hw": 0x16785109,
    }

# ABS CRC symbols in readelf symbol-table output.
elf_text = (
    "123: 00000000561b7fc2 0 NOTYPE GLOBAL DEFAULT ABS __crc_ieee80211_alloc_hw_nm\n"
    "124: 0000000016785109 0 NOTYPE GLOBAL DEFAULT ABS __crc_ieee80211_free_hw\n"
)
with patch.object(probe, "readelf", return_value=elf_text):
    assert probe.exports(Path("/dev/null")) == {
        "ieee80211_alloc_hw_nm": 0x561B7FC2,
        "ieee80211_free_hw": 0x16785109,
    }

# Preserve exactly 30 stock-Wi-Fi-related imported symbols, one CRC mismatch.
records = list(csv.DictReader((root / "ci/nevada-stock-wifi-vs-ath9k-htc-crcs.csv").open()))
assert len(records) == 30, len(records)
differ = [r for r in records if r["import_crc"] != r["stock_crc"]]
assert len(differ) == 1, differ
assert differ[0] == {
    "driver": "ath9k_htc.ko",
    "symbol": "ieee80211_alloc_hw_nm",
    "import_crc": "0x55ebf907",
    "stock_crc": "0x561b7fc2",
}
assert len(records) - len(differ) == 29
assert {r["driver"] for r in records} == {"ath.ko","ath9k_common.ko","ath9k_htc.ko"}
print("PASS: import entry parsing, export CRC parsing, 29 matching Wi-Fi imports, 1 mismatch")
print("IMPORTANT: stock binary files not present in CI; this is a fixture consistency test.")
