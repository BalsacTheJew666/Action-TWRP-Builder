#!/sbin/sh
# XT2615-1 Nevada OrangeFox vendor_boot flashable ZIP installer.
# EXPERIMENTAL. Only writes the current active slot after a verified
# persistent backup. No formatting, wiping, or cross-slot flashing.
#
# TWRP recovery arguments: api-version output-fd zipfile
OUTFD="${2:-}"
ZIPFILE="${3:-}"
EXPECTED="1d43d07a8353e0f7d198b4927d4f1db766c36ab8147eea288bc8b12842de621d"
SIZE=67108864
PAYLOAD="payload/vendor_boot.img"
WORK="/tmp/xt2615-fox-install-$$"

ui_print() {
  if [ -n "$OUTFD" ] && [ -e "/proc/self/fd/$OUTFD" ]; then
    printf 'ui_print %s\nui_print\n' "$1" > "/proc/self/fd/$OUTFD" 2>/dev/null || true
  fi
  printf '%s\n' "$1"
}
die() {
  ui_print "ERROR: $1"
  ui_print "Flashing stopped; working recovery should remain unchanged if writing has not begun."
  exit 1
}
getprop_safe() { getprop "$1" 2>/dev/null || true; }
hash_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  elif command -v busybox >/dev/null 2>&1; then
    busybox sha256sum "$1" | awk '{print $1}'
  else
    return 127
  fi
}
unzip_payload() {
  if command -v unzip >/dev/null 2>&1; then
    unzip -p "$1" "$2"
  elif command -v busybox >/dev/null 2>&1; then
    busybox unzip -p "$1" "$2"
  else
    return 127
  fi
}
size_file() { wc -c < "$1" | tr -d '[:space:]'; }
device_size() {
  if command -v blockdev >/dev/null 2>&1; then
    blockdev --getsize64 "$1" 2>/dev/null && return 0
  fi
  if command -v busybox >/dev/null 2>&1; then
    busybox blockdev --getsize64 "$1" 2>/dev/null && return 0
  fi
  return 1
}
ui_print "OrangeFox experimental XT2615-1 Nevada installer"
ui_print "Firmware: W1WNS36.18-114-1; Android 16"
ui_print "This replaces vendor_boot in CURRENT ACTIVE SLOT ONLY."
[ -n "$ZIPFILE" ] && [ -f "$ZIPFILE" ] || die "ZIP path missing."
command -v getprop >/dev/null 2>&1 || die "Android recovery getprop is unavailable."
command -v dd >/dev/null 2>&1 || die "dd unavailable in recovery."
command -v sync >/dev/null 2>&1 || die "sync unavailable in recovery."
command -v awk >/dev/null 2>&1 || die "awk unavailable in recovery."

# Reject a different Motorola device. Multiple property namespaces are
# considered because recovery's exact ro.product.* layout can vary.
DEVICE_PROPERTIES="$(getprop_safe ro.product.device) $(getprop_safe ro.product.vendor.device) $(getprop_safe ro.product.system.device) $(getprop_safe ro.product.product.device) $(getprop_safe ro.build.product)"
case "$DEVICE_PROPERTIES" in
  *nevada*) : ;;
  *) die "Device not reported as nevada: $DEVICE_PROPERTIES" ;;
esac
MODEL="$(getprop_safe ro.product.model)"
case "$MODEL" in
  *XT2615*|*"moto g play"*) : ;;
  "") ui_print "Model property unavailable; continuing with verified nevada device property." ;;
  *) die "Unexpected model $MODEL" ;;
esac

# Reject an obvious installed firmware mismatch if a ROM fingerprint is
# exposed by recovery. Recovery build properties are not definitive.
for PROPERTY in ro.build.fingerprint ro.vendor.build.fingerprint ro.system.build.fingerprint; do
  VALUE="$(getprop_safe "$PROPERTY")"
  case "$VALUE" in
    *W1WNS36.18-114-* )
      case "$VALUE" in
        *W1WNS36.18-114-1*) : ;;
        *) die "Firmware mismatch in $PROPERTY; requires W1WNS36.18-114-1." ;;
      esac
      ;;
  esac
done

SLOT="$(getprop_safe ro.boot.slot_suffix)"
if [ -z "$SLOT" ]; then
  RAW_SLOT="$(getprop_safe ro.boot.slot)"
  case "$RAW_SLOT" in a|b) SLOT="_$RAW_SLOT";; esac
fi
case "$SLOT" in
  _a|_b) ui_print "Active slot: $SLOT" ;;
  *) die "Cannot determine current active slot safely." ;;
esac
TARGET=""
for ROOT in /dev/block/by-name /dev/block/bootdevice/by-name; do
  if [ -b "$ROOT/vendor_boot$SLOT" ]; then
    TARGET="$ROOT/vendor_boot$SLOT"
    break
  fi
done
[ -n "$TARGET" ] || die "Current-slot vendor_boot block device not found."
TARGET_BYTES="$(device_size "$TARGET" || true)"
[ "$TARGET_BYTES" = "$SIZE" ] || die "Unexpected vendor_boot capacity: ${TARGET_BYTES:-unavailable} bytes."
ui_print "Verified active vendor_boot partition ($TARGET_BYTES bytes)."

# Always validate the entire image BEFORE touching any block device.
mkdir -p "$WORK" || die "Cannot create temporary directory."
IMAGE="$WORK/vendor_boot.img"
ui_print "Extracting and checking recovery image..."
unzip_payload "$ZIPFILE" "$PAYLOAD" > "$IMAGE" || die "ZIP image extraction failed."
[ "$(size_file "$IMAGE")" = "$SIZE" ] || die "Image length differs from 64 MiB."
IMAGE_SHA="$(hash_file "$IMAGE" || true)"
[ "$IMAGE_SHA" = "$EXPECTED" ] || die "Image SHA-256 mismatch."
MAGIC="$(dd if="$IMAGE" bs=8 count=1 2>/dev/null)"
[ "$MAGIC" = "VNDRBOOT" ] || die "Image is not a vendor_boot image."
ui_print "OrangeFox image SHA-256 verified."

# A persistently stored, correctly sized and readable backup is mandatory.
# Refuse silent backup to /tmp or / (these are ephemeral in recovery).
[ -d /sdcard ] || die "Internal storage is not mounted at /sdcard."
STORAGE_DEVICE="$(df -k /sdcard 2>/dev/null | awk 'END {print $1}')"
case "$STORAGE_DEVICE" in
  ""|tmpfs|rootfs|overlay|/dev/root) die "/sdcard appears unmounted or temporary; cannot keep a safe backup." ;;
esac
AVAIL_KB="$(df -k /sdcard 2>/dev/null | awk 'END {print $4}')"
case "$AVAIL_KB" in
  ''|*[!0-9]*) die "Cannot verify free space on internal storage." ;;
esac
[ "$AVAIL_KB" -ge 90000 ] || die "Need at least 90 MiB free on internal storage for backup."
BACKUP_DIR="/sdcard/OrangeFox-BACKUP-XT2615-1"
mkdir -p "$BACKUP_DIR" || die "Cannot create persistent backup folder."
BACKUP="$BACKUP_DIR/vendor_boot${SLOT}-TWRP-before-OrangeFox.img"
[ ! -e "$BACKUP" ] || die "Existing backup file found; refusing overwrite ($BACKUP)."
ui_print "Backing up current working vendor_boot$SLOT to internal storage..."
dd if="$TARGET" of="$BACKUP" bs=1048576 count=64 2>/dev/null || die "Cannot create backup."
sync
[ "$(size_file "$BACKUP")" = "$SIZE" ] || die "Backup is incomplete."
BACKUP_SHA="$(hash_file "$BACKUP" || true)"
[ -n "$BACKUP_SHA" ] || die "Cannot hash backup."
printf '%s  %s\n' "$BACKUP_SHA" "$(basename "$BACKUP")" > "$BACKUP_DIR/backup-sha256.txt" || die "Cannot write backup checksum."
sync
ui_print "Backup verified and saved: $BACKUP"
ui_print "Writing OrangeFox ONLY to vendor_boot$SLOT ..."
if ! dd if="$IMAGE" of="$TARGET" bs=1048576 count=64 2>/dev/null; then
  ui_print "Flash write failed; attempting automatic TWRP restoration."
  dd if="$BACKUP" of="$TARGET" bs=1048576 count=64 2>/dev/null || true
  sync
  die "Write failed. Check backup and vendor_boot before rebooting."
fi
sync
VERIFY_SHA="$(dd if="$TARGET" bs=1048576 count=64 2>/dev/null | sha256sum | awk '{print $1}')"
if [ "$VERIFY_SHA" != "$EXPECTED" ]; then
  ui_print "Written-image checksum mismatch. Restoring working TWRP..."
  dd if="$BACKUP" of="$TARGET" bs=1048576 count=64 2>/dev/null || true
  sync
  die "Readback check failed. Inspect/restoration required before reboot."
fi
ui_print "SUCCESS: OrangeFox flashed and readback verified."
ui_print "Your working TWRP backup is at: $BACKUP"
ui_print "Reboot DIRECTLY into recovery to test OrangeFox."
ui_print "DO NOT wipe or format any partitions."
rm -rf "$WORK"
exit 0
