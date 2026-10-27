#!/usr/bin/env python3
"""Static Atheros modversion audit against *sanitized* stock module CRC records.

The 30 supplied stock-Wi-Fi CRC reference entries were measured from the
user's SHA256-verified, stock mac80211.ko/cfg80211.ko binaries in an earlier
offline comparison. The actual stock ELF objects are intentionally NOT in GitHub.

This is NOT a live kernel audit or a module loader test.
Usage: script.py <path-to-driver-modules> <stock_wifi_reference.csv> <output.json>
"""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys

NAMES=("ath.ko","ath9k_common.ko","ath9k_hw.ko","ath9k_htc.ko")
REFERENCE_TARGET="ieee80211_alloc_hw_nm"
REFERENCE_CRC=0x561b7fc2

def readelf(path, *flags):
    return subprocess.run(
        ["readelf", *flags, str(path)], text=True,
        capture_output=True, check=True
    ).stdout

def section(path, name):
    # Parse section table via readelf with whitespace-safe ELF index handling.
    for line in readelf(path, "-SW").splitlines():
        parts=line.split()
        if len(parts)<7:
            continue
        # readelf -SW row: [ 12] __versions PROGBITS ... ; split gives
        # ['', '[', '12]', '__versions', ...] or ['[12]', '__versions',...].
        marker=parts.index(name) if name in parts else -1
        if marker<0 or len(parts)<=marker+4:
            continue
        # Values after section name: Type Address Off Size ES Flg Lk Inf Al
        offset=int(parts[marker+3],16)
        size=int(parts[marker+4],16)
        data=path.read_bytes()
        if offset+size>len(data):
            raise RuntimeError(f"{path}: malformed ELF section bounds")
        return data[offset:offset+size]
    raise RuntimeError(f"{path}: section {name} missing")

def imports(path):
    data=section(path,"__versions")
    if len(data)%64:
        raise RuntimeError(f"{path}: invalid __versions record width")
    out={}
    for offset in range(0,len(data),64):
        crc=struct.unpack_from("<Q",data,offset)[0]&0xffffffff
        symbol=data[offset+8:offset+64].split(b"\0",1)[0].decode("ascii")
        if symbol:
            if symbol in out and out[symbol]!=crc:
                raise RuntimeError(f"{path}: inconsistent duplicate import CRC for {symbol}")
            out[symbol]=crc
    return out

def exports(path):
    out={}
    for line in readelf(path,"-sW").splitlines():
        parts=line.split()
        if len(parts)>=8 and parts[-2]=="ABS" and parts[-1].startswith("__crc_"):
            out[parts[-1][6:]]=int(parts[1],16)&0xffffffff
    return out

def main():
    if len(sys.argv)!=4:
        raise SystemExit(__doc__)
    directory, refpath, resultpath=map(Path,sys.argv[1:])
    modules={name:directory/name for name in NAMES}
    for name,path in modules.items():
        if not path.is_file() or path.read_bytes()[:4]!=b"\x7fELF":
            raise RuntimeError(f"Missing or invalid ELF module: {path}")
    actual={name:imports(path) for name,path in modules.items()}
    reference=list(csv.DictReader(refpath.open()))
    if len(reference)!=30:
        raise RuntimeError(f"Expected precisely 30 saved stock Wi-Fi import rows; got {len(reference)}")
    if any(set(row)!={"driver","symbol","import_crc","stock_crc"} for row in reference):
        raise RuntimeError("Unexpected stock Wi-Fi CSV schema")
    verified=[]
    for row in reference:
        mod,sym=row["driver"],row["symbol"]
        if mod not in modules:
            raise RuntimeError(f"Unknown stock reference module: {mod}")
        expected=int(row["stock_crc"],16)
        observed=actual[mod].get(sym)
        verified.append({
            "module":mod,"symbol":sym,
            "candidate_crc":None if observed is None else f"0x{observed:08x}",
            "stock_crc":f"0x{expected:08x}",
            "match":observed==expected
        })
    if len(set((row["module"],row["symbol"]) for row in verified))!=30:
        raise RuntimeError("Duplicate stock Wi-Fi import reference rows")
    target=next((row for row in verified if row["module"]=="ath9k_htc.ko"
                and row["symbol"]==REFERENCE_TARGET),None)
    if target is None or target["stock_crc"]!=f"0x{REFERENCE_CRC:08x}":
        raise RuntimeError("Missing authoritative stock target CRC entry")
    ath_exports={}
    for name,path in modules.items():
        for sym,crc in exports(path).items():
            ath_exports.setdefault(sym,(name,crc))
    # vmlinux.symvers is from the *experiment*; do not count it as a live match.
    candidate_vmlinux={}
    symvers=directory/"vmlinux.symvers"
    if symvers.is_file():
        for line in symvers.read_text().splitlines():
            p=line.split()
            if len(p)>=3 and p[2]=="vmlinux":
                candidate_vmlinux[p[1]]=int(p[0],16)&0xffffffff
    from_ref={(r["module"],r["symbol"]) for r in verified}
    category=Counter()
    unchecked=[]
    for name, symbols in actual.items():
        for sym, crc in symbols.items():
            if (name,sym) in from_ref:
                category["stock_wifi_ref_match" if next(
                    r["match"] for r in verified if r["module"]==name and r["symbol"]==sym)
                    else "stock_wifi_ref_mismatch"]+=1
            elif sym in ath_exports:
                _,exp=ath_exports[sym]
                category["experimental_atheros_match" if exp==crc
                         else "experimental_atheros_mismatch"]+=1
            elif sym in candidate_vmlinux:
                exp=candidate_vmlinux[sym]
                category["candidate_core_symvers_match" if exp==crc
                         else "candidate_core_symvers_mismatch"]+=1
            else:
                category["unverified_import"]+=1
                unchecked.append({"module":name,"symbol":sym,"crc":f"0x{crc:08x}"})
    report={
        "status":"DIAGNOSTIC ONLY — NOT INSTALLABLE",
        "source_reference":"previous SHA256-verified stock wireless ELF audit, 30 sanitized imports",
        "total_import_entries":sum(len(x) for x in actual.values()),
        "reference_entries":len(reference),
        "stock_wifi_reference_verified":sum(x["match"] for x in verified),
        "stock_wifi_reference_failed":sum(not x["match"] for x in verified),
        "observed_categories":dict(sorted(category.items())),
        "stock_wifi_records":verified,
        "unverified_symbols":unchecked,
        "modules_sha256":{name:hashlib.sha256(path.read_bytes()).hexdigest()
                          for name,path in modules.items()},
        "warning":"Candidate vmlinux.symvers is NOT from target phone; 30 stock refs do not prove full live-kernel KMI, signing, CFI, vermagic, or module loader compatibility."
    }
    resultpath.write_text(json.dumps(report,indent=2)+"\n")
    summary=directory/"all-imports-summary.txt"
    summary.write_text(
        "STATIC AR9271 MODULE CRC AUDIT (NOT INSTALLABLE)\n"
        f"Total imports: {report['total_import_entries']}\n"
        f"Stock wireless reference matches: {report['stock_wifi_reference_verified']}/30\n"
        f"Stock wireless reference mismatches: {report['stock_wifi_reference_failed']}\n"
        +"\n".join(f"{k}: {v}" for k,v in sorted(category.items()))
        +"\nUnverified imports: "+str(len(unchecked))
        +"\nLive core KMI not checked: do not install/load/flash.\n"
    )
    print(summary.read_text())
    if any(not row["match"] for row in verified):
        raise SystemExit("FAIL: one or more stock Wi-Fi import CRCs do not match")
    if category["experimental_atheros_mismatch"] or category["candidate_core_symvers_mismatch"]:
        raise SystemExit("FAIL: internal module/self-consistency CRC mismatch")
    print("PASS: 30 sanitized stock wireless import CRCs match; driver NOT installable")

if __name__=="__main__":
    main()
