#!/usr/bin/env bash
# XT2615-1 research-only AR9271 compile with PUBLIC GKI retention superset, NOT installable.
# This is an OFFLINE COMPILE/CRC PROBE only. Do not install modules or flash.
set -Eeuo pipefail
: "${KERNEL_DIR:?Missing KERNEL_DIR}"
: "${OUT_DIR:?Missing OUT_DIR}"
: "${REFERENCE_CONFIG:?Missing REFERENCE_CONFIG}"

KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
REFERENCE_CONFIG="$(realpath "$REFERENCE_CONFIG")"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
AUDIT="$OUT_DIR/stock-abi-audit"
mkdir -p "$AUDIT"
cd "$KERNEL_DIR"
args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu-)

echo "=== Provenance ==="
git rev-parse HEAD
clang --version | head -1
sha256sum "$REFERENCE_CONFIG"
grep -Fqx 'CONFIG_CLANG_VERSION=140007' "$REFERENCE_CONFIG"
grep -Fqx 'CONFIG_LTO_CLANG_FULL=y' "$REFERENCE_CONFIG"
grep -Fqx 'CONFIG_MODVERSIONS=y' "$REFERENCE_CONFIG"
grep -Fqx 'CONFIG_TRIM_UNUSED_KSYMS=y' "$REFERENCE_CONFIG"
cp "$REFERENCE_CONFIG" "$AUDIT/config.stock-original"

# Upstream ATH9K_HTC conditionally selects MAC80211_LEDS when LEDS_CLASS=y.
# Our real Motorola module does not export LED trigger helpers. Remove ONLY
# that optional select in this temporary runner checkout, not on the phone.
python3 - <<'PY'
from pathlib import Path
p=Path('drivers/net/wireless/ath/ath9k/Kconfig')
s=p.read_text()
start=s.index('config ATH9K_HTC\n')
end=s.index('\nconfig ATH9K_HTC_DEBUGFS\n',start)
block=s[start:end]
old='\tselect MAC80211_LEDS if LEDS_CLASS=y || LEDS_CLASS=MAC80211\n'
if block.count(old)!=1:
    raise SystemExit('ATH9K_HTC Kconfig unexpectedly changed')
block=block.replace(old,'\t# ABI probe: do not select unavailable mac80211 LED triggers.\n')
p.write_text(s[:start]+block+s[end:])
PY
git diff -- drivers/net/wireless/ath/ath9k/Kconfig > "$AUDIT/ath9k-ledfree-source.patch"
test -s "$AUDIT/ath9k-ledfree-source.patch"

cp "$REFERENCE_CONFIG" "$OUT_DIR/.config"
# The genuine original vendor whitelist is unavailable. Use the verified
# official PUBLIC GKI exported-name superset plus 2 missing Atheros exports.
# This is NOT the original Motorola KMI; vendor-only exports may be absent.
: "${KMI_RESEARCH_SUPERSET:?Missing public research KMI whitelist}"
KMI_RESEARCH_SUPERSET="$(realpath "$KMI_RESEARCH_SUPERSET")"
test -r "$KMI_RESEARCH_SUPERSET"
test "$(wc -l < "$KMI_RESEARCH_SUPERSET")" -eq 8473
grep -Fqx 'rfkill_pause_polling' "$KMI_RESEARCH_SUPERSET"
grep -Fqx 'usb_get_urb' "$KMI_RESEARCH_SUPERSET"
scripts/config --file "$OUT_DIR/.config" --enable TRIM_UNUSED_KSYMS
scripts/config --file "$OUT_DIR/.config" --set-str UNUSED_KSYMS_WHITELIST "$KMI_RESEARCH_SUPERSET"
# FullLTO/Android clang-r450784e may require a heavier runner and toolchain.
# Use ThinLTO/Ubuntu Clang here to first isolate changes caused by stock config.
scripts/config --file "$OUT_DIR/.config" --disable LTO_CLANG_FULL
scripts/config --file "$OUT_DIR/.config" --enable LTO_CLANG_THIN
scripts/config --file "$OUT_DIR/.config" --enable WLAN
scripts/config --file "$OUT_DIR/.config" --enable WLAN_VENDOR_ATH
scripts/config --file "$OUT_DIR/.config" --module CFG80211
scripts/config --file "$OUT_DIR/.config" --module MAC80211
scripts/config --file "$OUT_DIR/.config" --module ATH9K_HTC
scripts/config --file "$OUT_DIR/.config" --disable MAC80211_LEDS
# The module's actual BTF (and PR #14's genksyms CRC control) prove that
# separately built stock mac80211 had TESTMODE callbacks and no debugfs one.
scripts/config --file "$OUT_DIR/.config" --enable NL80211_TESTMODE
scripts/config --file "$OUT_DIR/.config" --disable MAC80211_DEBUGFS
make "${args[@]}" olddefconfig

for sym in CFG80211 MAC80211 ATH9K_HTC ATH9K_COMMON ATH9K_HW ATH_COMMON; do
  grep -qx "CONFIG_${sym}=m" "$OUT_DIR/.config" ||
    { echo "::error::CONFIG_${sym} is not a module"; exit 2; }
done
for sym in CFI_CLANG MODVERSIONS LTO_CLANG_THIN; do
  grep -qx "CONFIG_${sym}=y" "$OUT_DIR/.config" ||
    { echo "::error::CONFIG_${sym} is not enabled"; exit 2; }
done
grep -qx '# CONFIG_MAC80211_LEDS is not set' "$OUT_DIR/.config" ||
  { echo "::error::LED configuration incorrectly enabled"; exit 2; }
grep -qx 'CONFIG_NL80211_TESTMODE=y' "$OUT_DIR/.config" ||
  { echo "::error::Stock module TESTMODE callback setting missing"; exit 2; }
grep -qx '# CONFIG_MAC80211_DEBUGFS is not set' "$OUT_DIR/.config" ||
  { echo "::error::Stock module lacks sta_add_debugfs callback"; exit 2; }
grep -qx 'CONFIG_TRIM_UNUSED_KSYMS=y' "$OUT_DIR/.config" ||
  { echo "::error::Public GKI research retention unexpectedly disabled"; exit 2; }
grep -Fqx "CONFIG_UNUSED_KSYMS_WHITELIST=\"$KMI_RESEARCH_SUPERSET\"" "$OUT_DIR/.config" ||
  { echo "::error::Public GKI symbol list path unexpectedly changed"; exit 2; }
cp "$OUT_DIR/.config" "$AUDIT/config.stock-based-diagnostic"

echo "=== Build stock-config-derived AR9271 module group ==="
make -j2 "${args[@]}" Image.gz modules

mods=(
  drivers/net/wireless/ath/ath9k/ath9k_htc.ko
  drivers/net/wireless/ath/ath9k/ath9k_common.ko
  drivers/net/wireless/ath/ath9k/ath9k_hw.ko
  drivers/net/wireless/ath/ath.ko
)
for mod in "${mods[@]}"; do
  [[ -s "$OUT_DIR/$mod" ]] || { echo "::error::Missing $mod"; exit 3; }
  cp "$OUT_DIR/$mod" "$AUDIT/"
done
cp "$OUT_DIR/Module.symvers" "$AUDIT/"
cp "$OUT_DIR/vmlinux.symvers" "$AUDIT/"
make -s "${args[@]}" kernelrelease > "$AUDIT/kernelrelease.txt"

# Import comparison to firmware-matched mac80211 from live-phone Build-ID audit.
# Do not patch or override any module's embedded CRC/version metadata.
python3 - "$AUDIT/ath9k_htc.ko" "$AUDIT/crc-results.txt" <<'PY'
import struct,sys
from pathlib import Path
module,output=map(Path,sys.argv[1:])
data=module.read_bytes()
if data[:6]!=b'\x7fELF\x02\x01':
    raise SystemExit('Not ELF64 little-endian')
offset=struct.unpack_from('<Q',data,40)[0]
size,num,names_index=struct.unpack_from('<HHH',data,58)
hdrs=[struct.unpack_from('<IIQQQQIIQQ',data,offset+i*size) for i in range(num)]
h=hdrs[names_index]
names=data[h[4]:h[4]+h[5]]
imports={}
for h in hdrs:
    if names[h[0]:].split(b'\x00',1)[0] != b'__versions':
        continue
    raw=data[h[4]:h[4]+h[5]]
    if len(raw)%64:
        raise SystemExit('Unexpected Linux 5.15 __versions width')
    for i in range(0,len(raw),64):
        symbol=raw[i+8:i+64].split(b'\x00',1)[0].decode('ascii')
        imports[symbol]=struct.unpack_from('<I',raw,i)[0]
    break
else:
    raise SystemExit('No module CRC import records')
stock=0x561b7fc2
actual=imports.get('ieee80211_alloc_hw_nm')
if actual is None:
    raise SystemExit('ieee80211_alloc_hw_nm is not imported')
led=[s for s in imports if s in (
    '__ieee80211_get_radio_led_name','__ieee80211_create_tpt_led_trigger')]
if led:
    raise SystemExit('Missing LED exports still required: '+str(led))
with output.open('w') as f:
    f.write(f'stock mac80211 CRC: 0x{stock:08x}\n')
    f.write(f'candidate import CRC: 0x{actual:08x}\n')
    f.write(f'compare: {"MATCH" if actual==stock else "MISMATCH"}\n')
    f.write(f'number of AR9271 symbol imports: {len(imports)}\n')
    f.write('missing LED imports: 0\n')
    f.write('NOTE: Match alone does not establish installability.\n')
print(output.read_text())
if actual != stock:
    raise SystemExit('Corrected TESTMODE AR9271 build still does not match stock CRC')
PY

# CSV is a sanitized, previously SHA-verified snapshot of stock Wi-Fi exports;
# this comparison does not substitute for a live kernel KMI check.
: "${STOCK_REFERENCE_CSV:?Missing stock Wi-Fi reference CSV}"
: "${CRC_AUDIT_SCRIPT:?Missing audit Python source}"
python3 "$CRC_AUDIT_SCRIPT" \
  "$AUDIT" "$STOCK_REFERENCE_CSV" "$AUDIT/all-imports-crc-audit.json"

{
  echo "PUBLIC GKI 8473-EXPORT SUPERSET DIAGNOSTIC ONLY; NOT INSTALLABLE, NOT STOCK KERNEL"
  echo "PUBLIC research allowlist SHA256 (NOT the original vendor symbollist.raw):"
  sha256sum "$KMI_RESEARCH_SUPERSET"
  echo "Reference sha256:"
  sha256sum "$REFERENCE_CONFIG"
  echo "Reference compiler: Android Clang 14.0.7 (r450784e)"
  echo "Used compiler:"
  clang --version | head -1
  echo "Source callback ABI corrected using NL80211_TESTMODE=y and MAC80211_DEBUGFS=n"
  echo "Stock FullLTO substituted with ThinLTO for this safe compile experiment"
  echo "Previous single-object tests showed identical CRC in ThinLTO and FullLTO"
  echo "Stock TRIM_UNUSED_KSYMS enabled with PUBLIC-GKI-plus-2 export-name superset, NOT COMPLETE original vendor whitelist"
  echo "CFG80211/MAC80211 built as temporary test modules, not device replacements"
  echo "Source:"
  git rev-parse HEAD
  echo "Resulting kernelrelease (not stock):"
  cat "$AUDIT/kernelrelease.txt"
  echo "Driver symbol CRC result:"
  cat "$AUDIT/crc-results.txt"
  echo "All 30 previously verified stock Wi-Fi import CRC comparisons:"
  cat "$AUDIT/all-imports-summary.txt"
  echo "DO NOT FLASH, insmod, create Magisk ZIP, OR REPLACE STOCK MODULES."
} > "$AUDIT/README-NOT-INSTALLABLE.txt"
cat "$AUDIT/README-NOT-INSTALLABLE.txt"

# Confirm that the compiler's own exported symvers truly includes both
# originally trimmed kernel functions, with the CRC values imported by the
# four compiled experimental Atheros ELF modules. Never override CRCs.
python3 - "$AUDIT/vmlinux.symvers" "$AUDIT/ath9k_htc.ko" "$AUDIT/reconstructed-export-proof.json" <<'PY'
import json, pathlib, struct, sys
symvers, module, output=map(pathlib.Path,sys.argv[1:])
export={}
for line in symvers.read_text().splitlines():
    p=line.split()
    if len(p)>=3 and p[2]=="vmlinux":
        export[p[1]]=int(p[0],16)
blob=module.read_bytes()
if blob[:6]!=b'\x7fELF\x02\x01':
    raise SystemExit("ath9k_htc.ko missing expected ELF64 little-endian header")
off=struct.unpack_from("<Q",blob,40)[0]
size,count,shidx=struct.unpack_from("<HHH",blob,58)
if size!=64 or not count:
    raise SystemExit("Unexpected ELF section header layout")
h=[struct.unpack_from("<IIQQQQIIQQ",blob,off+i*size) for i in range(count)]
shstr=blob[h[shidx][4]:h[shidx][4]+h[shidx][5]]
imports={}
for record in h:
    if shstr[record[0]:].split(b'\0',1)[0]!=b'__versions':
        continue
    raw=blob[record[4]:record[4]+record[5]]
    if len(raw)%64:
        raise SystemExit("Bad module __versions records")
    for k in range(0,len(raw),64):
        name=raw[k+8:k+64].split(b'\0',1)[0].decode('ascii')
        if name:
            imports[name]=struct.unpack_from("<I",raw,k)[0]
    break
else:
    raise SystemExit("Atheros ELF has no __versions imports")
out={}
for name in ("usb_get_urb","rfkill_pause_polling"):
    if name not in export or name not in imports:
        raise SystemExit(f"FAIL: {name} not both exported by candidate vmlinux and imported by ath9k_htc")
    core_crc,import_crc=export[name],imports[name]
    status="MATCH" if core_crc==import_crc else "MISMATCH"
    out[name]={"core_export_crc":f"0x{core_crc:08x}","ath9k_import_crc":f"0x{import_crc:08x}","status":status}
    print(f"NON-INSTALLABLE CANDIDATE: {name} export={core_crc:08x} import={import_crc:08x} {status}")
    if status!="MATCH":
        raise SystemExit("FAIL: Candidate exported CRC mismatches Atheros module import")
output.write_text(json.dumps({
  "status":"OFFLINE CANDIDATE SELF-CONSISTENCY ONLY, NOT LIVE DEVICE KMI",
  "source":"Motorola pinned kernel, Ubuntu Clang ThinLTO, public 8473-name research list",
  "exports":out,
  "critical_limitation":"Original Motorola KMI whitelist, stock FullLTO compiler, vendor source tree, actual kernelrelease and KernelSU compatibility NOT established; never flash"
},indent=2)+"\n")
print("PASS: both targeted kernel exports retained and self-consistent with ath9k_htc imports")
PY
