# XT2615-1 nevada — live USB/rfkill module export blockers

## Verified on the actual phone (Oct 27, 2026 02:35:30 UTC)

User ran the repository's **read-only** \`nevada-ar9271-live-loader-audit.sh\` with root. No kernel or Wi-Fi component was modified.

- Model: \`moto g play - 2026\`, \`nevada\`, firmware \`W1WNS36.18-114-1\`, Android 16, slot a.
- Running base: \`5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692\`; matches Google's pinned GKI build ID 14563692.
- \`modules_disabled=0\`, \`CONFIG_MODULES=y\`, \`CONFIG_MODVERSIONS=y\`, \`CONFIG_CFI_CLANG=y\`, \`CONFIG_LTO_CLANG=y\`, \`CONFIG_TRIM_UNUSED_KSYMS=y\`, \`CONFIG_MODULE_SIG=y\`, \`CONFIG_MODULE_SIG_FORCE=n\`.
- Current SELinux state was permissive (\`/sys/fs/selinux/enforce=0\`); do not change it for our tests.
- \`/proc/modules\` showed \`mac80211\`, \`cfg80211\`, and \`wlan_drv_gen4m_6835\` still loaded. Working internal Wi-Fi was not disturbed.

### The two remaining core-symbol imports

| Symbol | Required import CRC from experimental \`ath9k_htc.ko\` | Name in live \`/proc/kallsyms\` | \`__ksymtab_*\` or \`__crc_*\` name seen | Exact GKI 14563692 official export table |
| --- | --- | --- | --- | --- |
| \`rfkill_pause_polling\` | \`0x3939f8f0\` | yes | no | absent |
| \`usb_get_urb\` | \`0x3c85197c\` | yes | no | absent |

**Interpretation:** The functions are built into the running kernel but we did not find proof that the kernel exports them to third-party modules. The original stock Kconfig enables \`CONFIG_TRIM_UNUSED_KSYMS=y\`, which can remove exports that are not retained by the vendor's allowlist. The exact official GKI release \`vmlinux.symvers\` has 8,471 core symbols and does **not** export either. Root-visible function names are not sufficient evidence of exportability. Lack of \`__ksymtab_*\` in \`/proc/kallsyms\` is not by itself decisive, so this remains a strong hypothesis rather than conclusive evidence from the handset's export table.

The previously completed official full import audit found **30/30 real stock wireless CRC matches**, **67 self-consistent Atheros module CRC imports**, **134/136 exact GKI core CRC matches**, and the two not-exported symbols above. The previous 136/136 experimental-core symvers results are not evidence of the real phone's core exports.

## Why simply removing these function calls is unsafe

The pinned public Motorola kernel source at \`0fa176ca7f56c349b51acd83684284c02ced5854\` provides exact code-level provenance:

### \`usb_get_urb\` — USB request lifetime

- \`drivers/usb/core/urb.c\` provides \`usb_get_urb()\` and marks it \`EXPORT_SYMBOL_GPL\`.
- \`drivers/net/wireless/ath/ath9k/hif_usb.c\` calls \`usb_get_urb(tx_buf->urb)\` **before unlocking** \`tx_lock\`, killing outstanding USB requests, then freeing the request and associated buffers.
- This extra reference prevents premature URB destruction during the unlock/cancel window. Removing the call without redesigning locking and refcount management could cause use-after-free, double-free or corruption during unplug, deinitialization, or transmit stop.

### \`rfkill_pause_polling\` — radio polling lifetime

- \`net/rfkill/core.c\` defines and \`EXPORT_SYMBOL\`s \`rfkill_pause_polling()\`, which calls \`cancel_delayed_work_sync()\`.
- \`include/net/cfg80211.h\` implements \`wiphy_rfkill_stop_polling()\` as an inline wrapper that calls \`rfkill_pause_polling(wiphy->rfkill)\`.
- \`drivers/net/wireless/ath/ath9k/htc_drv_init.c\` invokes \`wiphy_rfkill_stop_polling(hw->wiphy)\` during \`ath9k_deinit_device()\` before hardware unregister/cleanup. Avoiding this may leave a polling worker running against deinitialized state. Do not stub it as a no-op.

The source's \`EXPORT_SYMBOL\` directives alone do **not** mean those exports survived the actual GKI build's \`TRIM_UNUSED_KSYMS\` or vendor KMI symbol list.

## Next engineering option

A robust stock-kernel driver would need **both legitimate exported entry points**, with correct modversion CRCs and compatible CFI/module metadata. We cannot safely spoof CRCs, rewrite loader checks, patch kernel memory, import unexported functions by address, or stub reference-counting/cleanup calls.

Given the observed trim settings and release symvers, the likely next route is a **reproducible, experimental custom GKI build** retaining these two symbols in its export/KMI list (and preserving any required KernelSU integration). It must remain **nonflashable research output** until its boot/recovery interfaces, root integration, stock Wi-Fi, and full module ABI have been independently validated, and the user explicitly approves any risky device-side flash.

This PR contains a **source-only, unprivileged GitHub Actions gate** to reproduce the two source call sites and verify absence from the official GKI export table. It does **not** build a replacement kernel or driver, and does not access the phone.

## Rule

**NO LOADING OR FLASHING** the existing experimental Atheros \`.ko\` files. Keep the working KernelSU, TWRP, OrangeFox, PBRP, SHRP, current Wi-Fi and phone kernel unchanged.
