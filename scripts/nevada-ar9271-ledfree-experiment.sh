#!/usr/bin/env bash
# Motorola XT2615-1 AR9271 LED-free *build experiment only*.
# Outputs are NOT suitable for installation, flashing, or Magisk.
set -Eeuo pipefail

: "${KERNEL_DIR:?Set KERNEL_DIR}"
: "${OUT_DIR:?Set OUT_DIR}"
mkdir -p "$OUT_DIR"
KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
cd "$KERNEL_DIR"

args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu-)
audit="$OUT_DIR/ar9271-ledfree-audit"
mkdir -p "$audit"

echo "=== Pinned Motorola source ==="
git rev-parse HEAD
clang --version | head -1

# In upstream Kconfig, ATH9K_HTC forces MAC80211_LEDS=y when LEDS_CLASS=y.
# Motorola's recovered stock mac80211 module lacks the two LED exports.
# Change ONLY this conditional 'select' inside the ATH9K_HTC stanza.
# Keep LEDS_CLASS itself unchanged for the rest of Android.
python3 - <<'PY'
from pathlib import Path
p = Path("drivers/net/wireless/ath/ath9k/Kconfig")
s = p.read_text()
begin = s.index("config ATH9K_HTC\n")
end = s.index("\nconfig ATH9K_HTC_DEBUGFS\n", begin)
block = s[begin:end]
old = "\tselect MAC80211_LEDS if LEDS_CLASS=y || LEDS_CLASS=MAC80211\n"
if block.count(old) != 1:
    raise SystemExit("Unexpected ATH9K_HTC Kconfig stanza; refusing to modify")
patched = block.replace(old, "\t# Experiment: do not force optional MAC80211 LED trigger ABI.\n")
p.write_text(s[:begin] + patched + s[end:])
PY
git diff -- drivers/net/wireless/ath/ath9k/Kconfig > "$audit/ath9k-ledfree-source.patch"
test -s "$audit/ath9k-ledfree-source.patch"

make "${args[@]}" gki_defconfig
cp "$OUT_DIR/.config" "$audit/config.gki-original"
# ThinLTO instead of Motorola's stock FullLTO ONLY to keep diagnostic CI memory low.
scripts/config --file "$OUT_DIR/.config" --disable LTO_CLANG_FULL
scripts/config --file "$OUT_DIR/.config" --enable LTO_CLANG_THIN
scripts/config --file "$OUT_DIR/.config" --enable WLAN
scripts/config --file "$OUT_DIR/.config" --enable WLAN_VENDOR_ATH
scripts/config --file "$OUT_DIR/.config" --module CFG80211
scripts/config --file "$OUT_DIR/.config" --module MAC80211
scripts/config --file "$OUT_DIR/.config" --module ATH9K_HTC
scripts/config --file "$OUT_DIR/.config" --disable MAC80211_LEDS
make "${args[@]}" olddefconfig

for s in CFG80211 MAC80211 ATH9K_HTC ATH9K_COMMON ATH9K_HW ATH_COMMON; do
  grep -qx "CONFIG_${s}=m" "$OUT_DIR/.config" || {
    echo "::error::Expected CONFIG_${s}=m"
    exit 2
  }
done
for s in USB CFI_CLANG MODVERSIONS LTO_CLANG_THIN; do
  grep -qx "CONFIG_${s}=y" "$OUT_DIR/.config" || {
    echo "::error::Expected CONFIG_${s}=y"
    exit 2
  }
done
grep -qx '# CONFIG_MAC80211_LEDS is not set' "$OUT_DIR/.config" || {
  echo "::error::MAC80211_LEDS remained enabled; LED-free experiment invalid"
  exit 2
}
cp "$OUT_DIR/.config" "$audit/config.ar9271-ledfree"

echo "=== Build an experimental kernel and modules solely for ABI diagnostics ==="
make -j2 "${args[@]}" Image.gz modules

mods=(
  drivers/net/wireless/ath/ath9k/ath9k_htc.ko
  drivers/net/wireless/ath/ath9k/ath9k_common.ko
  drivers/net/wireless/ath/ath9k/ath9k_hw.ko
  drivers/net/wireless/ath/ath.ko
)
for mod in "${mods[@]}"; do
  file="$OUT_DIR/$mod"
  test -s "$file" || { echo "::error::Missing $mod"; exit 3; }
  cp "$file" "$audit/"
done
test -s "$OUT_DIR/Module.symvers" || { echo "::error::Missing Module.symvers"; exit 4; }
cp "$OUT_DIR/Module.symvers" "$audit/"
cp "$OUT_DIR/vmlinux.symvers" "$audit/"

# Extract __versions records (ELF64 little-endian, modversions fixed-size names).
# This is a static check of the generated module, not a live device load test.
python3 - "$audit/ath9k_htc.ko" "$audit/ath9k_htc-imports.tsv" <<'PY'
from pathlib import Path
import struct, sys
data = Path(sys.argv[1]).read_bytes()
if data[:6] != b'\x7fELF\x02\x01':
    raise SystemExit('Not a little-endian ELF64 module')
shoff = struct.unpack_from('<Q', data, 40)[0]
entsize, nsects, sidx = struct.unpack_from('<HHH', data, 58)
sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff+i*entsize)
            for i in range(nsects)]
namesect = sections[sidx]
names = data[namesect[4]:namesect[4]+namesect[5]]
for s in sections:
    if names[s[0]:].split(b'\x00',1)[0] != b'__versions':
        continue
    raw = data[s[4]:s[4]+s[5]]
    if len(raw) % 64:
        raise SystemExit('Unexpected __versions entry width')
    records = {}
    for off in range(0,len(raw),64):
        part=raw[off:off+64]
        symbol=part[8:].split(b'\x00',1)[0].decode('ascii')
        records[symbol]=struct.unpack_from('<I',part)[0]
    Path(sys.argv[2]).write_text(''.join(
        f'{symbol}\t0x{crc:08x}\n' for symbol,crc in sorted(records.items())))
    for led in ('__ieee80211_create_tpt_led_trigger','__ieee80211_get_radio_led_name'):
        if led in records:
            raise SystemExit(f'LED import still present: {led}')
    print('PASS: Neither missing LED export is imported')
    print(f'AR9271 import count: {len(records)}')
    print('ieee80211_alloc_hw_nm import CRC:',
          f'0x{records.get("ieee80211_alloc_hw_nm",0):08x}')
    break
else:
    raise SystemExit('__versions section missing')
PY

{
  echo "SOURCE REVISION:"
  git rev-parse HEAD
  echo "KERNEL RELEASE (NOT STOCK):"
  make -s "${args[@]}" kernelrelease
  echo "COMPILER:"
  clang --version | head -1
  echo "OPTIONAL LED SUPPORT:"
  grep '^# CONFIG_MAC80211_LEDS is not set' "$OUT_DIR/.config"
  echo "AR9271 MODULES:"
  for mod in "${mods[@]}"; do
    echo "=== $mod ==="
    sha256sum "$OUT_DIR/$mod"
    readelf -p .modinfo "$OUT_DIR/$mod" |
      grep -E 'vermagic=|name=|depends=|firmware=' || true
  done
  echo "STOCK RECOVERY MAC80211 REFERENCE:"
  echo "ieee80211_alloc_hw_nm: 0x561b7fc2"
  echo "EXPERIMENTAL IMPORT CRC:"
  grep -w '^ieee80211_alloc_hw_nm' "$audit/ath9k_htc-imports.tsv" || true
  echo
  echo "NOT INSTALLABLE: source/toolchain/LTO/version/signature differ from stock."
  echo "Even CRC agreement alone does not prove live-module ABI compatibility."
} > "$audit/build-report.txt"

cat > "$audit/DO-NOT-INSTALL.txt" <<'WARNING'
DIAGNOSTIC BUILD ONLY. NO INSTALL/INSMOD/FLASH/MAGISK.
This test builds cfg80211/mac80211 and AR9271 against an experimental GKI.
Use the provided Atheros module binaries only for static CRC research.
Do not replace Motorola's existing wireless modules or change boot images.
WARNING
cat "$audit/build-report.txt"
