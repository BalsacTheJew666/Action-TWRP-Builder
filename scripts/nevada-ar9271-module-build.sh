#!/usr/bin/env bash
# AR9271/ath9k_htc kernel-driver compilation experiment ONLY.
# These modules are built alongside temporary, non-stock cfg80211/mac80211
# modules so the Atheros Kconfig dependencies can resolve. They MUST NOT be
# loaded into a user's phone or repackaged into a boot image as-is.
set -Eeuo pipefail

: "${KERNEL_DIR:?KERNEL_DIR is required}"
: "${OUT_DIR:?OUT_DIR is required}"
KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
mkdir -p "$OUT_DIR"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
cd "$KERNEL_DIR"
args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu-)

git rev-parse HEAD
clang --version | head -n 1
make "${args[@]}" gki_defconfig
cp "$OUT_DIR/.config" "$OUT_DIR/config.gki-original"

# Only a diagnostic compilation; this differs from the stock Android Clang
# Full-LTO configuration and CANNOT be used for phone installation.
scripts/config --file "$OUT_DIR/.config" --disable LTO_CLANG_FULL
scripts/config --file "$OUT_DIR/.config" --enable LTO_CLANG_THIN
scripts/config --file "$OUT_DIR/.config" --enable WLAN
scripts/config --file "$OUT_DIR/.config" --enable WLAN_VENDOR_ATH
scripts/config --file "$OUT_DIR/.config" --module CFG80211
scripts/config --file "$OUT_DIR/.config" --module MAC80211
scripts/config --file "$OUT_DIR/.config" --module ATH9K_HTC

make "${args[@]}" olddefconfig

for sym in CFG80211 MAC80211 ATH9K_HTC ATH9K_COMMON ATH9K_HW ATH_COMMON; do
  if grep -qx "CONFIG_${sym}=m" "$OUT_DIR/.config"; then
    echo "PASS: CONFIG_${sym}=m"
  else
    echo "::error::CONFIG_${sym}=m did not resolve"
    exit 2
  fi
done
for sym in USB CFI_CLANG MODVERSIONS LTO_CLANG_THIN; do
  grep -qx "CONFIG_${sym}=y" "$OUT_DIR/.config" || {
    echo "::error::CONFIG_${sym}=y did not resolve"
    exit 2
  }
done
cp "$OUT_DIR/.config" "$OUT_DIR/config.ar9271-experiment"

# Build all modules together to allow modpost to resolve wireless symbols.
# The produced cfg80211/mac80211 modules are NOT Motorola's stock modules.
make -j2 "${args[@]}" Image.gz modules

mods=(
  drivers/net/wireless/ath/ath9k/ath9k_htc.ko
  drivers/net/wireless/ath/ath9k/ath9k_common.ko
  drivers/net/wireless/ath/ath9k/ath9k_hw.ko
  drivers/net/wireless/ath/ath.ko
)
audit="$OUT_DIR/ar9271-audit"
mkdir -p "$audit"
{
  echo "Motorola source:"
  git rev-parse HEAD
  echo
  echo "Kernel release:"
  make -s "${args[@]}" kernelrelease
  echo
  echo "Compiler:"
  clang --version | head -n 1
  echo
  echo "Modules (non-flashable experiment):"
  for mod in "${mods[@]}"; do
    file="$OUT_DIR/$mod"
    test -s "$file" || { echo "::error::Missing $mod" >&2; exit 3; }
    echo "===== $mod ====="
    sha256sum "$file"
    readelf -p .modinfo "$file" | grep -E 'vermagic=|name=|depends=|firmware=' || true
  done
  echo
  echo "Other wireless modules from this experimental build are NOT stock replacements."
  echo "Do not load these modules or flash this kernel."
  echo "Next step: compare each module's imported CRCs against Motorola's actual"
  echo "cfg80211, mac80211, vendor exports, and firmware-matched kernel ABI."
} > "$audit/build-report.txt"
cp "$OUT_DIR/config.ar9271-experiment" "$audit/"
cp "$OUT_DIR/config.gki-original" "$audit/"
for mod in "${mods[@]}"; do
  cp "$OUT_DIR/$mod" "$audit/"
done
if [[ -s "$OUT_DIR/Module.symvers" ]]; then
  cp "$OUT_DIR/Module.symvers" "$audit/Module.symvers"
fi
cat > "$audit/DO-NOT-INSTALL.txt" <<'WARNING'
EXPERIMENTAL MODULES -- DO NOT INSTALL, LOAD, FLASH, OR ZIP FOR MAGISK.
The firmware-matched stock kernel, wireless module symbol ABI, and KernelSU
must be validated before creating usable NetHunter driver artifacts.
CFG80211/MAC80211 FROM THIS BUILD ARE NOT STOCK MODULE REPLACEMENTS.
WARNING
cat "$audit/build-report.txt"
