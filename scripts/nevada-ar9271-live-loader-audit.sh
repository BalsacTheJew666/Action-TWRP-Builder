#!/system/bin/sh
# Motorola XT2615-1 read-only NetHunter AR9271 module-loader preflight.
# Prints safe metadata and existence of *names* only (never kallsyms addresses).
# DOES NOT flash, insmod, modprobe, alter sysfs, reboot, setenforce, or patch.
# Usage (Termux):
#   su -c "sh /data/data/com.termux/files/home/nevada-ar9271-live-loader-audit.sh"
set -u
echo '===== XT2615-1 NEVADA NETHUNTER READ-ONLY LOADER AUDIT ====='
date -u 2>/dev/null || true
echo
echo '===== DEVICE AND KERNEL ====='
for K in ro.product.model ro.product.device ro.build.version.release ro.build.display.id ro.boot.slot_suffix ro.boot.verifiedbootstate; do
  V="$(getprop "$K" 2>/dev/null || true)"
  printf '%s=%s\n' "$K" "$V"
done
printf 'uname -r='
uname -r
printf 'uname -m='
uname -m
printf 'effective_uid='
id -u 2>/dev/null || true
echo
echo '===== MODULE LOAD POLICY (READ ONLY) ====='
for P in \
 /proc/sys/kernel/modules_disabled \
 /proc/sys/kernel/module_sig_enforce \
 /sys/module/module/parameters/sig_enforce \
 /sys/module/module/parameters/allow_missing_symbols \
 /proc/sys/kernel/kptr_restrict \
 /sys/fs/selinux/enforce; do
  if [ -r "$P" ]; then
    printf '%s=' "$P"
    cat "$P" 2>/dev/null || echo unknown
  else
    echo "$P=not_available"
  fi
done
echo
echo '===== LOADED NETWORK/MODULE NAMES (NO KERNEL POINTERS) ====='
if [ -r /proc/modules ]; then
  awk '$1 ~ /^(cfg80211|mac80211|ath|ath9k|ath9k_htc|usbcore|rfkill|wlan_drv.*)$/ {print $1, "size="$2, "usecount="$3}' /proc/modules
else
  echo '/proc/modules not readable'
fi
echo
echo '===== VERIFIED STOCK MODULE BUILD ID NOTE DIGESTS ====='
for M in cfg80211 mac80211; do
  P="/sys/module/$M/notes/.note.gnu.build-id"
  if [ -r "$P" ]; then
    printf '%s note_sha256=' "$M"
    sha256sum "$P" 2>/dev/null | awk '{print $1}'
  else
    printf '%s note_sha256=unavailable\n' "$M"
  fi
done
echo
echo '===== ROOT-READABLE KALLSYMS NAME PRESENCE (NEVER ADDRESSES) ====='
if [ ! -r /proc/kallsyms ]; then
  echo 'Kallsyms not readable; cannot determine target exports'
else
  for S in rfkill_pause_polling usb_get_urb; do
    # A raw symbol name is NOT the same as an exported module symbol.
    # __ksymtab_$S is stronger evidence, but still cannot verify CRC.
    awk -v sym="$S" '
      $3==sym {ordinary++}
      $3=="__ksymtab_" sym {ksymtab++}
      $3=="__crc_" sym {crcname++}
      END {
        printf "symbol=%s function_name_seen=%s export_ksymtab_seen=%s crc_name_seen=%s\n",
          sym,ordinary+0,ksymtab+0,crcname+0
      }' /proc/kallsyms 2>/dev/null ||
      printf 'symbol=%s lookup=unavailable\n' "$S"
  done
fi
echo
echo '===== RELEVANT KERNEL CONFIG SETTINGS ====='
if [ -r /proc/config.gz ] && command -v zcat >/dev/null 2>&1; then
  zcat /proc/config.gz 2>/dev/null |
    grep -E '^(CONFIG_(MODULES|MODVERSIONS|MODULE_SIG|MODULE_SIG_FORCE|CFI_CLANG|LTO_CLANG|TRIM_UNUSED_KSYMS|KALLSYMS|USB|RFKILL|KPROBES)=|# CONFIG_(MODULES|MODVERSIONS|MODULE_SIG|MODULE_SIG_FORCE|CFI_CLANG|LTO_CLANG|TRIM_UNUSED_KSYMS|KALLSYMS|USB|RFKILL|KPROBES) is not set)' ||
    true
else
  echo 'Kernel .config not accessible'
fi
echo
echo '===== SAFETY / INTERPRETATION ====='
echo 'Read-only inspection completed; no device setting was changed.'
echo 'Missing names may result from kallsyms restriction or export trimming.'
echo 'Export-name presence does NOT verify required CRCs, module CFI/vermagic, or safe loading.'
echo 'Official GKI 14563692 lacks rfkill_pause_polling and usb_get_urb in vmlinux.symvers.'
echo 'No AR9271 modules should be installed, insmodded or flashed yet.'
