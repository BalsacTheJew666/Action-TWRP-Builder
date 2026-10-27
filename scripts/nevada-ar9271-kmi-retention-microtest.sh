#!/usr/bin/env bash
# XT2615-1 nevada: model Linux 5.15 automatic KMI export trimming, no build.
# Uses the pinned public Motorola kernel's actual gen_autoksyms.sh script.
# This is a tiny two-export *proof* whitelist, NOT a replacement for the
# missing complete vendor ABI symbol list. Never use it to build a flash image.
set -Eeuo pipefail

: "${KERNEL_DIR:?Set KERNEL_DIR to the verified public Motorola source}"
: "${STOCK_CONFIG:?Set STOCK_CONFIG to the SHA256-verified stock .config}"
: "${RESULT_DIR:?Set RESULT_DIR to an output directory}"
KERNEL_DIR="$(realpath "$KERNEL_DIR")"
STOCK_CONFIG="$(realpath "$STOCK_CONFIG")"
mkdir -p "$RESULT_DIR"
RESULT_DIR="$(realpath "$RESULT_DIR")"

SOURCE_SHA=0fa176ca7f56c349b51acd83684284c02ced5854
CONFIG_SHA=e3cdaf997a7e2eb70e441944bdfd9af359aa82e8a2d5cb9534d2bce5fcd4a78a
test "$(git -C "$KERNEL_DIR" rev-parse HEAD)" = "$SOURCE_SHA"
printf '%s  %s\n' "$CONFIG_SHA" "$STOCK_CONFIG" | sha256sum -c -
grep -Fxq 'CONFIG_TRIM_UNUSED_KSYMS=y' "$STOCK_CONFIG"
grep -Fxq 'CONFIG_MODVERSIONS=y' "$STOCK_CONFIG"
grep -Fxq 'CONFIG_MODULE_SIG_PROTECT=y' "$STOCK_CONFIG"
grep -Fxq 'CONFIG_CFI_CLANG=y' "$STOCK_CONFIG"
test -f "$KERNEL_DIR/scripts/gen_autoksyms.sh"

# Prove the original source *declares* these exports and the Atheros driver
# consumes them (this alone does NOT prove the phone exports them).
grep -Fq 'EXPORT_SYMBOL(rfkill_pause_polling);' "$KERNEL_DIR/net/rfkill/core.c"
grep -Fq 'EXPORT_SYMBOL_GPL(usb_get_urb);' "$KERNEL_DIR/drivers/usb/core/urb.c"
grep -Fq 'rfkill_pause_polling(wiphy->rfkill);' "$KERNEL_DIR/include/net/cfg80211.h"
grep -Fq 'usb_get_urb(tx_buf->urb);' "$KERNEL_DIR/drivers/net/wireless/ath/ath9k/hif_usb.c"

printf 'rfkill_pause_polling\nusb_get_urb\n' > "$RESULT_DIR/PROOF-ONLY-MINIMAL-WHITELIST.txt"
: > "$RESULT_DIR/CONTROL-EMPTY-WHITELIST.txt"

for variant in control retained; do
    work="$RESULT_DIR/$variant"
    mkdir -p "$work/include/config"
    if [[ "$variant" == control ]]; then
        whitelist="$RESULT_DIR/CONTROL-EMPTY-WHITELIST.txt"
    else
        whitelist="$RESULT_DIR/PROOF-ONLY-MINIMAL-WHITELIST.txt"
    fi

    # This is an isolated micro-test of gen_autoksyms.sh using a minimal,
    # synthetic auto.conf; NOT Kconfig, kernel configuration or compilation.
    printf 'CONFIG_MODVERSIONS=y\nCONFIG_UNUSED_KSYMS_WHITELIST="%s"\n' \
      "$whitelist" > "$work/include/config/auto.conf"
    (
      cd "$work"
      abs_srctree="$KERNEL_DIR" \
        /bin/sh "$KERNEL_DIR/scripts/gen_autoksyms.sh" "$work/autoksyms.h"
    )
    grep -Fxq '#define __KSYM_module_layout 1' "$work/autoksyms.h"
done

for name in rfkill_pause_polling usb_get_urb; do
  if grep -Fxq "#define __KSYM_$name 1" "$RESULT_DIR/control/autoksyms.h"; then
    echo "ERROR: $name unexpectedly in empty-whitelist control" >&2
    exit 2
  fi
  grep -Fxq "#define __KSYM_$name 1" "$RESULT_DIR/retained/autoksyms.h" || {
    echo "ERROR: $name not retained by proposed whitelist" >&2
    exit 3
  }
  echo "PASS: CONFIG_TRIM_UNUSED_KSYMS whitelist retains $name"
done

{
  echo "MOTOROLA XT2615-1 — SOURCE-ONLY KMI RETENTION MICRO-TEST"
  echo "Source revision: $SOURCE_SHA"
  echo "Reference original stock Kconfig checksum: $CONFIG_SHA"
  echo "Kernel source's gen_autoksyms.sh recognizes two required exports."
  echo "Important: the 2-name whitelist is DELIBERATELY INCOMPLETE."
  echo "A full reproducible custom GKI needs the correct full stock ABI"
  echo "symbol list, verified kernel configuration and compatible toolchain."
  echo "This result says NOTHING about the actual running phone's exports."
  echo "DO NOT USE THIS MICRO-TEST OUTPUT TO BUILD A FLASHABLE KERNEL."
  echo "DO NOT INSMOD, FORCE LOAD, PATCH CRC/VERMAGIC OR FLASH."
} | tee "$RESULT_DIR/README-SOURCE-ONLY-NOT-A-KERNEL.txt"
