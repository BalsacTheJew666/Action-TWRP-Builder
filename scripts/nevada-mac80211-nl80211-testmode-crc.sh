#!/usr/bin/env bash
# Device-safe stock Wi-Fi type provenance experiment. FullLTO, one object only.
# No patched CRC, no installation, no boot image or flashable module.
set -Eeuo pipefail
: "${KERNEL_DIR:?Set KERNEL_DIR to verified public Motorola kernel source}"
: "${STOCK_CONFIG:?Set STOCK_CONFIG to original downloaded config}"
: "${OUT_ROOT:?Set OUT_ROOT to workspace}"
KERNEL_DIR="$(realpath "$KERNEL_DIR")"
STOCK_CONFIG="$(realpath "$STOCK_CONFIG")"
mkdir -p "$OUT_ROOT"
OUT_ROOT="$(realpath "$OUT_ROOT")"
EVIDENCE="$OUT_ROOT/evidence"
mkdir -p "$EVIDENCE"
git -C "$KERNEL_DIR" rev-parse HEAD | tee "$EVIDENCE/source-sha.txt"
clang --version | head -1 | tee "$EVIDENCE/clang-version.txt"
sha256sum "$STOCK_CONFIG" | tee "$EVIDENCE/original-config.sha256"

for state in off on; do
  echo "======== NL80211_TESTMODE: $state ========"
  out="$OUT_ROOT/$state"
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
    scripts/config --file "$out/.config" --disable MAC80211_DEBUGFS
    if [[ "$state" = on ]]; then
      scripts/config --file "$out/.config" --enable NL80211_TESTMODE
    else
      scripts/config --file "$out/.config" --disable NL80211_TESTMODE
    fi
    args=(ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- O="$out")
    make -j2 "${args[@]}" olddefconfig
    grep -qx 'CONFIG_MAC80211=m' "$out/.config"
    grep -qx 'CONFIG_CFG80211=m' "$out/.config"
    grep -qx 'CONFIG_MODVERSIONS=y' "$out/.config"
    grep -qx 'CONFIG_LTO_CLANG_FULL=y' "$out/.config"
    grep -qx '# CONFIG_MAC80211_DEBUGFS is not set' "$out/.config"
    if [[ "$state" = on ]]; then
      grep -qx 'CONFIG_NL80211_TESTMODE=y' "$out/.config"
    else
      grep -qx '# CONFIG_NL80211_TESTMODE is not set' "$out/.config"
    fi
    cp "$out/.config" "$EVIDENCE/$state-resolved.config"
    make -j2 "${args[@]}" prepare scripts
    make -j2 "${args[@]}" KBUILD_SYMTYPES=1 net/mac80211/main.o
  )
  test -s "$out/net/mac80211/main.o.symversions"
  test -s "$out/net/mac80211/main.symtypes"
  cp "$out/net/mac80211/main.o.symversions" "$EVIDENCE/$state-main.o.symversions"
  cp "$out/net/mac80211/main.symtypes" "$EVIDENCE/$state-main.symtypes"
  python3 - "$state" "$out/net/mac80211/main.o.symversions" "$EVIDENCE/$state-result.txt" <<'PY'
import pathlib,re,sys
state=sys.argv[1]
symvers=pathlib.Path(sys.argv[2]).read_text()
target='__crc_ieee80211_alloc_hw_nm'
m=re.findall(r'\b'+re.escape(target)+r'\s*=\s*0x([0-9a-fA-F]+)',symvers)
if len(m)!=1:
  raise SystemExit(f'Missing or ambiguous CRC for {target}: {m}')
crc=int(m[0],16) & 0xffffffff
stock=0x561b7fc2
out=f'NL80211_TESTMODE={state}\nCRC=0x{crc:08x}\nSTOCK_CRC=0x{stock:08x}\nMATCHES_STOCK={str(crc==stock).lower()}\n'
pathlib.Path(sys.argv[3]).write_text(out)
print(out)
PY
done
{
 echo 'Moto XT2615-1 stock mac80211 Type/CRC control. No installable output.'
 echo 'Source git SHA:'; cat "$EVIDENCE/source-sha.txt"
 echo 'Compiler:'; cat "$EVIDENCE/clang-version.txt"
 echo 'Verbatim stock BTF local members include testmode_cmd and testmode_dump.'
 echo 'Existing stock iee80211_ops: 115 members, 920-byte contiguous pointer layout.'
 cat "$EVIDENCE/off-result.txt" "$EVIDENCE/on-result.txt"
 echo 'Type trace digests:'
 sha256sum "$EVIDENCE/"*-main.symtypes
 echo 'WARNING: One exported symbol matching does not certify all imports, CFI, KMI, vermagic or loader requirements.'
} | tee "$EVIDENCE/README-NOT-INSTALLABLE.txt"
