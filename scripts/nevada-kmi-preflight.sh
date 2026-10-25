#!/usr/bin/env bash
# XT2615-1: PUBLIC-SOURCE kernel symbol/KMI preflight only.
# No proprietary Motorola files, boot packaging, flashing, or root modifications.
set -Eeuo pipefail

: "${KERNEL_DIR:?Set KERNEL_DIR}"
: "${OUT_DIR:?Set OUT_DIR}"
mkdir -p "$OUT_DIR"
KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
cd "$KERNEL_DIR"

args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 LLVM_IAS=1 CROSS_COMPILE=aarch64-linux-gnu-)
echo "=== Source ==="
git rev-parse HEAD
head -n 6 Makefile
clang --version | head -n 1

make "${args[@]}" gki_defconfig
cp "$OUT_DIR/.config" "$OUT_DIR/config.gki-original"

# Preserve the stock GKI *kernel* treatment of wireless frameworks:
# cfg80211/mac80211 are NOT built into vmlinux. Motorola provides separately
# loaded modules, and those must never be replaced in this experiment.
for s in CFG80211 MAC80211 ATH9K_HTC RT2800USB RTL8187 MT7601U; do
  scripts/config --file "$OUT_DIR/.config" --disable "$s"
done

# Stock firmware uses Full LTO with Android Clang 14.0.7.
# ThinLTO is a resource-constrained *diagnostic* build only and can change KMI.
scripts/config --file "$OUT_DIR/.config" --disable LTO_CLANG_FULL
scripts/config --file "$OUT_DIR/.config" --enable LTO_CLANG_THIN
make "${args[@]}" olddefconfig

required=(LTO_CLANG_THIN CFI_CLANG MODVERSIONS MODULE_SIG USB_CONFIGFS_F_HID)
for s in "${required[@]}"; do
  grep -qx "CONFIG_${s}=y" "$OUT_DIR/.config" || {
    echo "::error::Required CONFIG_${s}=y was not retained"
    exit 2
  }
done

for s in CFG80211 MAC80211 ATH9K_HTC RT2800USB RTL8187 MT7601U LTO_CLANG_FULL; do
  if grep -Eq "^CONFIG_${s}=(y|m)$" "$OUT_DIR/.config"; then
    echo "::error::Must not enable CONFIG_${s} in KMI preflight"
    exit 2
  fi
done
echo "Verified: stock-style modular Wi-Fi framework is NOT built into this test kernel"

echo "=== Building read-only-analysis artifacts; no boot image produced ==="
make -j2 "${args[@]}" Image.gz
test -s "$OUT_DIR/vmlinux.symvers" || {
  echo "::error::vmlinux.symvers missing; cannot compare exported kernel symbol CRCs"
  exit 3
}
test -s "$OUT_DIR/arch/arm64/boot/Image.gz"

make -s "${args[@]}" kernelrelease > "$OUT_DIR/kernelrelease.txt"
{
  echo "Kernel source:"
  git rev-parse HEAD
  echo "Built kernel release:"
  cat "$OUT_DIR/kernelrelease.txt"
  echo "Toolchain:"
  clang --version | head -n 1
  echo "Built-in kernel exported symbol count:"
  wc -l < "$OUT_DIR/vmlinux.symvers"
  echo "LTO configuration:"
  grep -E '^(CONFIG_LTO_CLANG_THIN=|CONFIG_CFI_CLANG=|CONFIG_MODVERSIONS=|CONFIG_MODULE_SIG=)' "$OUT_DIR/.config"
  echo "Wireless GKI choices:"
  grep -E '^(# CONFIG_CFG80211 is not set|# CONFIG_MAC80211 is not set)' "$OUT_DIR/.config" || true
  echo
  echo "THIS IS A NON-FLASHABLE, GKI-BASED KMI EXPERIMENT."
  echo "It is NOT a stock-identical kernel: compiler, ThinLTO and release differ."
  echo "Do not flash Image.gz and do not change boot/vendor_boot/init_boot."
} > "$OUT_DIR/kmi-preflight.txt"
sha256sum "$OUT_DIR/vmlinux.symvers" "$OUT_DIR/.config" > "$OUT_DIR/kmi-preflight.sha256"
cat "$OUT_DIR/kmi-preflight.txt"
