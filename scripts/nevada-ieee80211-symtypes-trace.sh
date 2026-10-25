#!/usr/bin/env bash
# XT2615-1: source-level genksyms type trace for ieee80211_alloc_hw_nm.
# Safe analysis only; no drivers/boot images built or loaded onto the device.
set -Eeuo pipefail

: "${KERNEL_DIR:?Set KERNEL_DIR}"
: "${WORK_DIR:?Set WORK_DIR}"
: "${STOCK_CONFIG:?Set STOCK_CONFIG}"
KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
STOCK_CONFIG="$(realpath "$STOCK_CONFIG")"
mkdir -p "$WORK_DIR"
WORK_DIR="$(cd "$WORK_DIR" && pwd)"
REPORT="$WORK_DIR/abi-types"
mkdir -p "$REPORT"
cd "$KERNEL_DIR"

args=(ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu-)
git rev-parse HEAD > "$REPORT/kernel-source-commit.txt"
clang --version | head -1 > "$REPORT/toolchain.txt"
sha256sum "$STOCK_CONFIG" > "$REPORT/stock-config.sha256"

for flavor in gki stock; do
  echo "=== Building genksyms signature trace: $flavor ==="
  out="$WORK_DIR/$flavor"
  mkdir -p "$out"

  if [[ "$flavor" == stock ]]; then
    cp "$STOCK_CONFIG" "$out/.config"
  else
    make -j2 "${args[@]}" O="$out" gki_defconfig
  fi

  # Compile ONLY net/mac80211/main.o with independent outputs.
  # Normal Android loads cfg80211/mac80211 separately, not in vmlinux.
  scripts/config --file "$out/.config" --enable WLAN
  scripts/config --file "$out/.config" --module CFG80211
  scripts/config --file "$out/.config" --module MAC80211
  scripts/config --file "$out/.config" --enable MODVERSIONS

  # CI environment cannot recreate Motorola's private symbol whitelist.
  # ThinLTO is only for keeping LLVM compilation bounded in CI.
  scripts/config --file "$out/.config" --disable TRIM_UNUSED_KSYMS
  scripts/config --file "$out/.config" --set-str UNUSED_KSYMS_WHITELIST ""
  scripts/config --file "$out/.config" --disable LTO_CLANG_FULL
  scripts/config --file "$out/.config" --enable LTO_CLANG_THIN

  make -j2 "${args[@]}" O="$out" olddefconfig
  for s in CFG80211 MAC80211; do
    grep -qx "CONFIG_${s}=m" "$out/.config" || {
      echo "::error::CONFIG_${s} did not resolve as a module for $flavor"
      exit 2
    }
  done
  grep -qx 'CONFIG_MODVERSIONS=y' "$out/.config" || exit 2

  make -j2 "${args[@]}" O="$out" prepare scripts
  make -j2 "${args[@]}" O="$out" KBUILD_SYMTYPES=1 net/mac80211/main.o

  trace="$out/net/mac80211/main.symtypes"
  if [[ ! -s "$trace" ]]; then
    echo "::error::genksyms did not produce $trace"
    find "$out/net/mac80211" -maxdepth 1 -type f -printf '%f %s bytes\n' || true
    exit 3
  fi
  cp "$trace" "$REPORT/$flavor-mac80211-main.symtypes"
  cp "$out/.config" "$REPORT/$flavor-config.resolved"
  sha256sum "$trace"
  {
    echo "=== $flavor: ieee80211_alloc_hw_nm symbols in genksyms dump ==="
    grep -n 'ieee80211_alloc_hw_nm' "$trace" || true
    echo "=== $flavor: ieee80211_ops type in genksyms dump ==="
    grep -n -m 12 'ieee80211_ops' "$trace" || true
  } > "$REPORT/$flavor-type-excerpts.txt"
done

diff -u "$REPORT/gki-mac80211-main.symtypes" \
  "$REPORT/stock-mac80211-main.symtypes" \
  > "$REPORT/gki-vs-stock-symtypes.diff" || status=$?
if [[ "${status:-0}" -gt 1 ]]; then
  echo "::error::diff failed" && exit 4
fi

{
 echo "XT2615 NEVADA — GENKSYMS ABI-TYPE DIAGNOSTIC (NOT INSTALLABLE)"
 echo "Motorola source commit:"
 cat "$REPORT/kernel-source-commit.txt"
 echo "Build compiler:"
 cat "$REPORT/toolchain.txt"
 echo "Reference module export CRC: ieee80211_alloc_hw_nm=0x561b7fc2"
 echo "Prior experiment import CRC: ieee80211_alloc_hw_nm=0x55ebf907"
 echo "NOTE: No Motorola stock source-level symtypes dump is available."
 echo "We compare candidate GKI-vs-stock-CONFIG source type expansion only."
 echo "A zero diff does NOT prove the module will load."
 echo "Source code and private firmware revisions may differ."
 echo "These files cannot be used as modules, a boot image, or a patch."
 echo "Selected source-level traces:"
 cat "$REPORT/gki-type-excerpts.txt"
 cat "$REPORT/stock-type-excerpts.txt"
 echo "Diff bytes:"
 wc -c "$REPORT/gki-vs-stock-symtypes.diff"
} > "$REPORT/README-NO-FLASH.txt"
cat "$REPORT/README-NO-FLASH.txt"
