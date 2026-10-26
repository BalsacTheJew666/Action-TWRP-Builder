#!/usr/bin/env bash
# Research-only: isolate LTO versus source-dependent symbol CRC differences.
set -Eeuo pipefail
: "${KERNEL_DIR:?Missing KERNEL_DIR}"
: "${OUT_ROOT:?Missing OUT_ROOT}"
: "${STOCK_CONFIG:?Missing STOCK_CONFIG}"
KERNEL_DIR="$(realpath "$KERNEL_DIR")"
STOCK_CONFIG="$(realpath "$STOCK_CONFIG")"
mkdir -p "$OUT_ROOT"
OUT_ROOT="$(realpath "$OUT_ROOT")"
RESULTS="$OUT_ROOT/evidence"
mkdir -p "$RESULTS"
git -C "$KERNEL_DIR" rev-parse HEAD > "$RESULTS/source-commit.txt"
clang --version | head -1 > "$RESULTS/compiler.txt"
sha256sum "$STOCK_CONFIG" > "$RESULTS/stock-config.sha256"
grep -qx 'CONFIG_MODVERSIONS=y' "$STOCK_CONFIG"
grep -qx 'CONFIG_LTO_CLANG_FULL=y' "$STOCK_CONFIG"

for mode in none thin full; do
  echo "==== LTO MODE: $mode ===="
  out="$OUT_ROOT/build-$mode"
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
    scripts/config --file "$out/.config" --disable LTO_CLANG_FULL
    scripts/config --file "$out/.config" --disable LTO_CLANG_THIN
    scripts/config --file "$out/.config" --disable LTO_NONE
    case "$mode" in
      none) scripts/config --file "$out/.config" --enable LTO_NONE ;;
      thin) scripts/config --file "$out/.config" --enable LTO_CLANG_THIN ;;
      full) scripts/config --file "$out/.config" --enable LTO_CLANG_FULL ;;
    esac
    args=(ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu- O="$out")
    make -j2 "${args[@]}" olddefconfig
    grep -qx 'CONFIG_MODVERSIONS=y' "$out/.config"
    grep -qx 'CONFIG_MAC80211=m' "$out/.config"
    grep -qx 'CONFIG_CFG80211=m' "$out/.config"
    case "$mode" in
      none) grep -qx 'CONFIG_LTO_NONE=y' "$out/.config" ;;
      thin) grep -qx 'CONFIG_LTO_CLANG_THIN=y' "$out/.config" ;;
      full) grep -qx 'CONFIG_LTO_CLANG_FULL=y' "$out/.config" ;;
    esac
    cp "$out/.config" "$RESULTS/$mode-config.resolved"
    make -j2 "${args[@]}" prepare scripts
    # Compile just one object; no vmlinux, .ko or phone install.
    make -j2 "${args[@]}" KBUILD_SYMTYPES=1 net/mac80211/main.o
  )
  obj="$out/net/mac80211/main.o"
  test -s "$obj"
  file "$obj" | tee "$RESULTS/$mode-object-type.txt"
  syms="$out/net/mac80211/main.symtypes"
  test -s "$syms"
  cp "$syms" "$RESULTS/$mode-main.symtypes"

  python3 - "$obj" "$mode" "$RESULTS/$mode-result.txt" <<'PY'
import pathlib,re,subprocess,sys
obj=pathlib.Path(sys.argv[1]); mode=sys.argv[2]; output=pathlib.Path(sys.argv[3])
target='__crc_ieee80211_alloc_hw_nm'
if mode in ('thin','full'):
    versions=pathlib.Path(str(obj)+'.symversions')
    if not versions.is_file():
        raise SystemExit(f'Missing genksyms output: {versions}')
    text=versions.read_text(errors='replace')
    values=re.findall(r'\b'+re.escape(target)+r'\s*=\s*0x([0-9a-fA-F]+)',text)
else:
    raw=subprocess.run(['readelf','-sW',str(obj)],text=True,capture_output=True,check=True).stdout
    values=[]
    for line in raw.splitlines():
        parts=line.split()
        if len(parts)>=8 and parts[-1]==target and parts[-2]=='ABS':
            values.append(parts[1])
if len(values)!=1:
    raise SystemExit(f'Expected exactly one {target} CRC for mode={mode}, found {values}')
actual=int(values[0],16)&0xffffffff
stock=0x561b7fc2
result=f'mode={mode}\nexported_crc=0x{actual:08x}\nstock_mac80211_crc=0x{stock:08x}\nmatch={str(actual==stock).lower()}\n'
output.write_text(result)
print(result)
PY
done

{
  echo "Motorola source commit:"
  cat "$RESULTS/source-commit.txt"
  echo "CI compiler:"
  cat "$RESULTS/compiler.txt"
  echo "Phone firmware reference CRC: 0x561b7fc2"
  echo "Prior full ThinLTO test module CRC: 0x55ebf907"
  echo "Prior GKI-config single-object no-LTO CRC: 0x856d772a"
  echo
  for mode in none thin full; do
    cat "$RESULTS/$mode-result.txt"
  done
  echo "Symtypes hashes:"
  sha256sum "$RESULTS/"*-main.symtypes
  echo "Not stock ABI matched: private symbol whitelist and original compiler unavailable."
  echo "NEVER FLASH, insmod, sign, package or install these diagnostic objects."
} > "$RESULTS/README-ABI-CRC-RESULTS.txt"
cat "$RESULTS/README-ABI-CRC-RESULTS.txt"
