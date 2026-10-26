#!/usr/bin/env bash
# Source-only ABI test. No device access, kernel flash, insmod, .ko installation.
# Compare the exported CRC of mac80211's ieee80211_alloc_hw_nm while toggling
# the optional sta_add_debugfs callback under CONFIG_MAC80211_DEBUGFS.
set -Eeuo pipefail
: "${KERNEL_DIR:?KERNEL_DIR is required}"
: "${STOCK_CONFIG:?STOCK_CONFIG is required}"
: "${OUT_ROOT:?OUT_ROOT is required}"

KERNEL_DIR="$(realpath "$KERNEL_DIR")"
STOCK_CONFIG="$(realpath "$STOCK_CONFIG")"
mkdir -p "$OUT_ROOT"
OUT_ROOT="$(realpath "$OUT_ROOT")"
REPORT="$OUT_ROOT/evidence"
mkdir -p "$REPORT"
sha256sum "$STOCK_CONFIG" | tee "$REPORT/stock-config.sha256"
git -C "$KERNEL_DIR" rev-parse HEAD | tee "$REPORT/source-commit.txt"
clang --version | head -1 | tee "$REPORT/compiler.txt"

for state in off on; do
  echo "===== CONFIG_MAC80211_DEBUGFS=$state ====="
  out="$OUT_ROOT/build-$state"
  mkdir -p "$out"
  cp "$STOCK_CONFIG" "$out/.config"
  (
    cd "$KERNEL_DIR"
    scripts/config --file "$out/.config" --enable WLAN
    scripts/config --file "$out/.config" --module CFG80211
    scripts/config --file "$out/.config" --module MAC80211
    scripts/config --file "$out/.config" --enable MODVERSIONS
    scripts/config --file "$out/.config" --disable TRIM_UNUSED_KSYMS
    scripts/config --file "$out/.config" --set-str UNUSED_KSYMS_WHITELIST ""
    scripts/config --file "$out/.config" --disable LTO_CLANG_THIN
    scripts/config --file "$out/.config" --disable LTO_NONE
    scripts/config --file "$out/.config" --enable LTO_CLANG_FULL
    if [[ "$state" == off ]]; then
      scripts/config --file "$out/.config" --disable MAC80211_DEBUGFS
    else
      scripts/config --file "$out/.config" --enable MAC80211_DEBUGFS
    fi
    args=(ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- O="$out")
    make -j2 "${args[@]}" olddefconfig
    grep -qx "CONFIG_MODVERSIONS=y" "$out/.config"
    grep -qx "CONFIG_LTO_CLANG_FULL=y" "$out/.config"
    grep -qx "CONFIG_MAC80211=m" "$out/.config"
    grep -qx "CONFIG_CFG80211=m" "$out/.config"
    if [[ "$state" == off ]]; then
      grep -qx '# CONFIG_MAC80211_DEBUGFS is not set' "$out/.config"
    else
      grep -qx 'CONFIG_MAC80211_DEBUGFS=y' "$out/.config"
    fi
    cp "$out/.config" "$REPORT/$state-config.resolved"
    make -j2 "${args[@]}" prepare scripts
    make -j2 "${args[@]}" KBUILD_SYMTYPES=1 net/mac80211/main.o
  )
  obj="$out/net/mac80211/main.o"
  types="$out/net/mac80211/main.symtypes"
  versions="$obj.symversions"
  test -s "$obj"
  test -s "$types"
  test -s "$versions"
  cp "$types" "$REPORT/$state-main.symtypes"
  cp "$versions" "$REPORT/$state-main.symversions"
  python3 - "$versions" "$state" "$REPORT/$state-result.txt" <<'PY'
import pathlib,re,sys
versions=pathlib.Path(sys.argv[1]).read_text()
state=sys.argv[2]
target='__crc_ieee80211_alloc_hw_nm'
values=re.findall(r'\b'+re.escape(target)+r'\s*=\s*0x([0-9a-fA-F]+)',versions)
if len(values)!=1:
    raise SystemExit(f'Expected exactly one {target} CRC; found {values}')
crc=int(values[0],16)&0xffffffff
ref=0x561b7fc2
result=f'MAC80211_DEBUGFS={state}\nCRC=0x{crc:08x}\nSTOCK_REFERENCE=0x{ref:08x}\nMATCHES_STOCK={str(crc==ref).lower()}\n'
pathlib.Path(sys.argv[3]).write_text(result)
print(result)
PY
done

{
  echo "FullLTO MAC80211_DEBUGFS toggle comparison, Motorola public source"
  echo "Actual stock module reference CRC = 0x561b7fc2"
  echo "Stock split BTF struct ieee80211_ops size=920, members=115"
  echo "Local BTF has sta_add -> sta_remove -> sta_notify (no sta_add_debugfs)"
  echo "Only module-local string offsets are trusted; external base BTF differs."
  cat "$REPORT/off-result.txt" "$REPORT/on-result.txt"
  echo "Type trace digests:"
  sha256sum "$REPORT/"*-main.symtypes
  echo "No-KO build; no installable modules or boot images were produced."
  echo "One matching CRC is insufficient to establish full device compatibility."
} | tee "$REPORT/README-DEBUGFS-CRC.txt"
