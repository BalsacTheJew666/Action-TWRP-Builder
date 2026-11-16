# XT2615-1 / Nevada: reproduce the missing AR9271 kernel exports without device changes

## Live evidence

The actual rooted Moto G Play 2026 (Android 16, kernel \`5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692\`) completed the read-only stock module ELF witness audit:

- 181 already-loaded stock \`.ko\` files read successfully; 181 mount aliases collapsed.
- **82 of 101 distinct AR9271 candidate core CRC requirements** corroborated by existing stock-module \`__versions\` imports, with **0 conflicts**.
- **19 names lack stock-module witnesses**, comprising 16 USB symbols, \`rfkill_pause_polling\`, \`device_release_driver\`, \`kmemdup\`.
- Independent official GKI **build 14563692** \`vmlinux.symvers\` matched **134 of 136** core import instances from the four experimental Atheros modules. Of the 19 without loaded-module witnesses, **17 already have an official GKI export CRC match**.
- The two outstanding official-release exports are **\`usb_get_urb\`** and **\`rfkill_pause_polling\`**.
- Both function *names* exist in the running device's kallsyms, but \`__ksymtab_...\` and \`__crc_...\` entries were not found despite other \`__ksymtab_\` entries being visible.
- Running stock config is \`CONFIG_TRIM_UNUSED_KSYMS=y\`, \`CONFIG_CFI_CLANG=y\`, \`CONFIG_MODVERSIONS=y\`, \`CONFIG_MODULE_SIG_PROTECT=y\`, \`CONFIG_LTO_CLANG_FULL=y\`.

This is strong evidence the two exports are trimmed or otherwise inaccessible to \`ath9k_htc.ko\`. **Do not substitute a phone function address for an actual \`EXPORT_SYMBOL\`; do not force-load the driver.**

## Exact mechanism under test

The original stock config refers to a private, unavailable build-time whitelist:
\`CONFIG_UNUSED_KSYMS_WHITELIST="/mnt/disks/build-disk/src/android/common-android13-5.15-2025-05/out/android13-5.15/common/abi_symbollist.raw"\`.

The pinned public Motorola source \`0fa176ca7f56c349b51acd83684284c02ced5854\` includes the original Linux \`scripts/gen_autoksyms.sh\`. That script consumes \`CONFIG_UNUSED_KSYMS_WHITELIST\` and generates macros \`__KSYM_<export>=1\` to retain eligible \`EXPORT_SYMBOL\` definitions.

The module lifecycle requires:
- \`usb_get_urb()\`: the Atheros USB driver increments the URB refcount during TX cancellations and later decrements it in the cleanup path; removing the call without redesigning synchronization risks memory corruption. The public source marks it \`EXPORT_SYMBOL_GPL(usb_get_urb)\`.
- \`rfkill_pause_polling()\`: the cfg80211 wrapper invokes it during hardware deinit; the kernel code synchronizes rfkill polling. Do not replace it with a no-op. The public source marks it \`EXPORT_SYMBOL(rfkill_pause_polling)\`.

## GitHub Actions micro-test

The workflow fetches only the **SHA-pinned public Motorola source**, checks the **SHA256-pinned stock base .config**, and runs the **real source \`gen_autoksyms.sh\`** in a tiny isolated workspace. It compares:

- **Control:** empty whitelist => only \`__KSYM_module_layout\` for modversions; no two targets.
- **Proof:** a two-name whitelist containing \`usb_get_urb\` and \`rfkill_pause_polling\` => both generated retention macros must appear.

This **does not compile** the kernel, modules, or a boot image, and never accesses the handset. It answers the narrow question whether the pinned kernel source's trimming mechanism can be directed to retain these exports.

**Critical:** The tiny two-name proof whitelist is NOT a valid full GKI/Motorola KMI whitelist. Building a phone kernel with *only* those two names could trim thousands of stock vendor exports, break device boot, and break internal Wi-Fi. Never flash any product of this experiment. We need the **complete genuine stock symbol list**, a fully compatible source/build environment, correct root integration and a validated boot/recovery rollback plan before beginning a safe device kernel candidate build.

## Next development gates

1. Recover or reconstruct the **complete official/vendor KMI retention whitelist**. The exact original artifact \`abi_symbollist.raw\` is not in the public source checkout.
2. Build an experimental matching GKI **with all required stock exports plus both newly retained symbols**, with the original Android-Clang build environment and exact kernel config and no overridden CRCs.
3. Validate the resulting \`vmlinux.symvers\` against all stock Wi-Fi modules, vendor-loaded module dependencies and 233 Atheros import instances, plus CFI/LTO, module signing and exact target \`vermagic\`.
4. Preserve the currently working KernelSU Next and TWRP/OrangeFox and do not attempt any flashing without explicit user approval and correct backups.

This repository PR stops at the **first, device-safe source-level gate**.
