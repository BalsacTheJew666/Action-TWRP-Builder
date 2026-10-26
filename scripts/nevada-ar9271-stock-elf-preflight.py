#!/usr/bin/env python3
"""Read-only AR9271 module import CRC audit against preserved stock Wi-Fi exports.

Usage:
  python3 scripts/nevada-ar9271-stock-elf-preflight.py \
      stock-mac80211.ko stock-cfg80211.ko nevada-stockconfig-ar9271-abi.zip \
      [report.json]

No ELF is executed, patched, loaded, installed, or flashed. Readelf is required.
"""
from __future__ import annotations
from collections import Counter
from pathlib import Path
import hashlib
import json
import struct
import subprocess
import sys
import tempfile
import zipfile

STOCK_SHA = {
    "mac80211.ko": "f404b741cda2012557d567efec688148e7d4578e127b1de4f347e7f8f8445e87",
    "cfg80211.ko": "85f877d3866f0668fea72a725e1506fd0979d9e636e94e69c0f3328f917dcb90",
}
DRIVERS = ("ath.ko", "ath9k_common.ko", "ath9k_hw.ko", "ath9k_htc.ko")


def readelf(path: Path, *args: str) -> str:
    return subprocess.run(
        ["readelf", *args, str(path)], check=True, capture_output=True, text=True
    ).stdout


def section(path: Path, name: str) -> bytes:
    for line in readelf(path, "-SW").splitlines():
        p = line.split()
        if len(p) > 6 and p[1] == name:
            offset, length = int(p[4], 16), int(p[5], 16)
            data = path.read_bytes()
            if offset + length > len(data):
                raise ValueError("ELF section exceeds file length")
            return data[offset:offset + length]
    raise ValueError(f"{path}: missing {name}")


def exports(path: Path) -> dict[str, int]:
    result = {}
    for line in readelf(path, "-sW").splitlines():
        p = line.split()
        if len(p) >= 8 and p[-2] == "ABS" and p[-1].startswith("__crc_"):
            result[p[-1][6:]] = int(p[1], 16) & 0xFFFFFFFF
    return result


def imports(path: Path) -> dict[str, int]:
    data = section(path, "__versions")
    if len(data) % 64:
        raise ValueError(f"{path}: __versions length not divisible by 64")
    result = {}
    for offset in range(0, len(data), 64):
        crc = struct.unpack_from("<Q", data, offset)[0] & 0xFFFFFFFF
        name = data[offset + 8:offset + 64].split(b"\0", 1)[0].decode("ascii")
        if name:
            result[name] = crc
    return result


def run(mac: Path, cfg: Path, archive: Path) -> dict:
    for label, path in (("mac80211.ko", mac), ("cfg80211.ko", cfg)):
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if digest != STOCK_SHA[label]:
            raise ValueError(f"Unexpected stock {label} SHA256: {digest}")
    providers = {sym: (crc, "stock mac80211.ko") for sym, crc in exports(mac).items()}
    for sym, crc in exports(cfg).items():
        providers.setdefault(sym, (crc, "stock cfg80211.ko"))
    rows = []
    with tempfile.TemporaryDirectory() as directory, zipfile.ZipFile(archive) as z:
        core = {}
        for line in z.read("vmlinux.symvers").decode().splitlines():
            parts = line.split("\t")
            if len(parts) >= 3 and parts[2] == "vmlinux":
                core[parts[1]] = int(parts[0], 16)
        paths = {}
        for name in DRIVERS:
            p = Path(directory) / name
            p.write_bytes(z.read(name))
            paths[name] = p
        ath_exports = {}
        for name, path in paths.items():
            for sym, crc in exports(path).items():
                ath_exports.setdefault(sym, (crc, name))
        for name, path in paths.items():
            for sym, used_crc in sorted(imports(path).items()):
                if sym in providers:
                    target_crc, provider = providers[sym]
                    group = "stock_wifi_match" if target_crc == used_crc else "stock_wifi_mismatch"
                elif sym in ath_exports:
                    target_crc, provider = ath_exports[sym]
                    group = "ath_module_match" if target_crc == used_crc else "ath_module_mismatch"
                elif sym in core:
                    target_crc, provider = core[sym], "experimental vmlinux.symvers"
                    group = "candidate_core_match" if target_crc == used_crc else "candidate_core_mismatch"
                else:
                    target_crc, provider, group = None, "unresolved", "unresolved"
                rows.append({
                    "driver": name, "symbol": sym,
                    "import_crc": f"0x{used_crc:08x}",
                    "provider_crc": f"0x{target_crc:08x}" if target_crc is not None else None,
                    "provider": provider, "category": group,
                })
    return {
        "summary": dict(sorted(Counter(row["category"] for row in rows).items())),
        "import_count": len(rows),
        "warning": "EXPERIMENTAL core symvers are not from the live kernel; no install authorization",
        "records": rows,
    }


def main() -> None:
    if len(sys.argv) not in (4, 5):
        raise SystemExit(__doc__)
    output = Path(sys.argv[4]) if len(sys.argv) == 5 else Path("nevada-ar9271-abi-report.json")
    result = run(*(Path(x) for x in sys.argv[1:4]))
    output.write_text(json.dumps(result, indent=2) + "\n")
    print("Total imports:", result["import_count"])
    print("Summary:", result["summary"])
    for row in result["records"]:
        if "mismatch" in row["category"] or row["category"] == "unresolved":
            print("CHECK:", json.dumps(row, sort_keys=True))
    print(result["warning"])
    print("Report:", output)


if __name__ == "__main__":
    main()
