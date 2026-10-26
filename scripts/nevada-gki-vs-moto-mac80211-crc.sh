#!/usr/bin/env bash
# Compare exported ieee80211_alloc_hw_nm CRCs from public GKI and Motorola source.
# Compile only net/mac80211/main.o; no .ko, boot image, or installable artifact.
set -Eeuo pipefail
: "${MOTO_SRC:?Set MOTO_SRC}"
: "${GKI_SRC:?Set GKI_SRC}"
: "${WORK_DIR:?Set WORK_DIR}"
MOTO_SRC="$(realpath "$MOTO_SRC")"
GKI_SRC="$(realpath "$GKI_SRC")"
mkdir -p "$WORK_DIR"
WORK_DIR="$(cd "$WORK_DIR" && pwd)"
report="$WORK_DIR/gki-vs-motorola-mac80211"
mkdir -p "$report"
export LC_ALL=C
target_crc=561b7fc2

for flavor in motorola gki; do
  if [[ "$flavor" == motorola ]]; then src="$MOTO_SRC"; else src="$GKI_SRC"; fi
  out="$WORK_DIR/out-$flavor"
  mkdir -p "$out"
  echo "=== $flavor: source SHA, config and toolchain ==="
  git -C "$src" rev-parse HEAD | tee "$report/$flavor-commit.txt"
  (cd "$src"; clang --version | head -1) > "$report/$flavor-compiler.txt"
  (
    cd "$src"
    args=(ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- O="$out")
    make -j2 "${args[@]}" gki_defconfig

    # Same diagnostic flags on both sources. This is NOT the device's
    # firmware compiler, true KMI build or loadable module preparation.
    scripts/config --file "$out/.config" --enable WLAN
    scripts/config --file "$out/.config" --module CFG80211
    scripts/config --file "$out/.config" --module MAC80211
    scripts/config --file "$out/.config" --enable MODVERSIONS
    scripts/config --file "$out/.config" --disable TRIM_UNUSED_KSYMS
    scripts/config --file "$out/.config" --set-str UNUSED_KSYMS_WHITELIST ""
    # CRC analysis uses readelf on the resulting object. ThinLTO emits
    # LLVM bitcode (.o), which is NOT an ELF object; disable LTO for
    # this targeted genksyms-only comparison, equally on both sources.
    scripts/config --file "$out/.config" --disable LTO_CLANG_FULL
    scripts/config --file "$out/.config" --disable LTO_CLANG_THIN
    scripts/config --file "$out/.config" --enable LTO_NONE
    make -j2 "${args[@]}" olddefconfig
    grep -qx 'CONFIG_CFG80211=m' "$out/.config"
    grep -qx 'CONFIG_MAC80211=m' "$out/.config"
    grep -qx 'CONFIG_MODVERSIONS=y' "$out/.config"
    grep -qx 'CONFIG_LTO_NONE=y' "$out/.config"

    make -j2 "${args[@]}" prepare scripts
    make -j2 "${args[@]}" KBUILD_SYMTYPES=1 net/mac80211/main.o
  )

  obj="$out/net/mac80211/main.o"
  symtypes="$out/net/mac80211/main.symtypes"
  test -s "$obj"
  test -s "$symtypes"
  file "$obj" | tee "$report/$flavor-object-filetype.txt"
  readelf -h "$obj" | grep -E 'Class:|Type:|Machine:'
  readelf -sW "$obj" > "$report/$flavor-main-symbols.txt"
  grep -F '__crc_ieee80211_alloc_hw_nm' "$report/$flavor-main-symbols.txt" |
    tee "$report/$flavor-target-export.txt"
  # Verify there is exactly one absolute CRC symbol and compare it.
  python3 - "$report/$flavor-main-symbols.txt" "$report/$flavor-result.txt" "$target_crc" <<'PY'
import re,sys
from pathlib import Path
entries=[]
for line in Path(sys.argv[1]).read_text().splitlines():
  if not line.strip().endswith(' __crc_ieee80211_alloc_hw_nm'): continue
  p=line.split()
  if len(p)>=8 and p[6]=='ABS':
    entries.append(int(p[1],16))
if len(entries)!=1:
  raise SystemExit('Unable to prove exactly one ABS genksyms CRC for ieee80211_alloc_hw_nm')
reference=int(sys.argv[3],16)
value=entries[0]&0xffffffff
result=f'candidate=0x{value:08x}\nreference=0x{reference:08x}\nmatch={value==reference}\n'
Path(sys.argv[2]).write_text(result)
print(result)
PY
  cp "$symtypes" "$report/$flavor-main.symtypes"
  cp "$out/.config" "$report/$flavor-resolved.config"
done

diff -u "$report/motorola-main.symtypes" "$report/gki-main.symtypes"   > "$report/motorola-vs-gki-main.symtypes.diff" || [[ "$?" == 1 ]]
for relative in net/mac80211/main.c include/net/mac80211.h include/linux/ieee80211.h; do
  n="${relative//\//_}"
  diff -u "$MOTO_SRC/$relative" "$GKI_SRC/$relative"     > "$report/motorola-vs-gki-$n.diff" || [[ "$?" == 1 ]]
done

{
 echo "XT2615-1 Nevada GKI/Motorola mac80211 TYPE CRC COMPARISON"
 echo "Stock firmware's module export: ieee80211_alloc_hw_nm=0x$target_crc"
 echo "Stock Wi-Fi modules: verified Build-ID matches live loaded drivers"
 echo "Candidate GKI branch: android13-5.15-2025-05, pinned commit"
 cat "$report/gki-commit.txt"
 echo "Candidate Motorola kernel branch: android-16-release-w1wn36.18-114, pinned commit"
 cat "$report/motorola-commit.txt"
 echo "Motorola object CRC:"
 cat "$report/motorola-result.txt"
 echo "GKI object CRC:"
 cat "$report/gki-result.txt"
 echo "GENKSYMS trace hashes:"
 sha256sum "$report/"*-main.symtypes
 echo "GENKSYMS trace diff size:"
 wc -c "$report/motorola-vs-gki-main.symtypes.diff"
 echo "LIMITATIONS: neither source tree is proven to match firmware build exactly."
 echo "NOT INSTALLABLE; do not forge CRC or vermagic, insmod or flash."
} > "$report/README-CRC-COMPARISON.txt"
cat "$report/README-CRC-COMPARISON.txt"
