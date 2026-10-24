#!/usr/bin/env bash
# XT2615-1 / nevada: non-flashable NetHunter kernel build experiment.
set -Eeuo pipefail

: "${KERNEL_DIR:?Set KERNEL_DIR to checked-out Motorola kernel source}"
: "${OUT_DIR:?Set OUT_DIR to a build output directory}"
ENABLE_WIFI="${ENABLE_WIFI:-true}"
PATCH_DIR="${PATCH_DIR:-}"
mkdir -p "$OUT_DIR"
KERNEL_DIR="$(cd "$KERNEL_DIR" && pwd)"
OUT_DIR="$(cd "$OUT_DIR" && pwd)"
cd "$KERNEL_DIR"

echo "=== Moto G Play 2026: kernel source and build identity ==="
git log -1 --format='%H %s'
head -n 6 Makefile
grep -E '^(ARCH|LLVM|KERNEL_DIR)=' build.config.mtk.aarch64

if [[ -n "$PATCH_DIR" ]]; then
  PATCH_DIR="$(cd "$PATCH_DIR" && pwd)"
  shopt -s nullglob
  patches=("$PATCH_DIR"/*.patch)
  if (("${#patches[@]}" )); then
    for patch in "${patches[@]}"; do
      echo "Checking patch: $(basename "$patch")"
      git apply --check "$patch"
      git apply "$patch"
    done
  else
    echo "No explicit source patches supplied; using supported in-tree Kconfig features."
  fi
fi

build_args=(O="$OUT_DIR" ARCH=arm64 LLVM=1 LLVM_IAS=1
            CROSS_COMPILE=aarch64-linux-gnu-)
make "${build_args[@]}" gki_defconfig
cp "$OUT_DIR/.config" "$OUT_DIR/config.stock-gki"

enable=(
  USB_GADGET USB_CONFIGFS USB_CONFIGFS_F_HID
  USB_CONFIGFS_MASS_STORAGE USB_CONFIGFS_ECM USB_CONFIGFS_RNDIS
  BT BT_RFCOMM
)
if [[ "$ENABLE_WIFI" == true ]]; then
  enable+=(
    WLAN WIRELESS CFG80211 MAC80211
    WLAN_VENDOR_ATH ATH9K_HTC
    WLAN_VENDOR_RALINK RT2X00 RT2800USB
    WLAN_VENDOR_REALTEK RTL8187
    WLAN_VENDOR_MEDIATEK MT7601U
  )
fi

echo "=== Requesting NetHunter features in generated configuration ==="
for sym in "${enable[@]}"; do
  scripts/config --file "$OUT_DIR/.config" --enable "$sym"
done
make "${build_args[@]}" olddefconfig

# A requested symbol quietly disappearing is a real missing dependency,
# not proof NetHunter functionality exists. Fail the build rather than lie.
failed=0
for sym in "${enable[@]}"; do
  if grep -qx "CONFIG_${sym}=y" "$OUT_DIR/.config"; then
    echo "OK: CONFIG_${sym}=y"
  else
    echo "::error::CONFIG_${sym} did not resolve to =y after olddefconfig"
    failed=1
  fi
done
if ((failed)); then
  echo "Resolve Kconfig dependencies in a separate source patch before proceeding."
  exit 2
fi

echo "=== Build ARM64 kernel (test only) ==="
make -j2 "${build_args[@]}" Image.gz
make -s "${build_args[@]}" kernelrelease > "$OUT_DIR/kernelrelease.txt"
test -s "$OUT_DIR/arch/arm64/boot/Image.gz"
sha256sum "$OUT_DIR/arch/arm64/boot/Image.gz" > "$OUT_DIR/Image.gz.sha256"
echo "=== Build completed; NOT a flashable boot.img or vendor_boot.img ==="
cat "$OUT_DIR/kernelrelease.txt"
cat "$OUT_DIR/Image.gz.sha256"
