# XT2615-1 nevada: reproduce stock mac80211 NL80211_TESTMODE callback ABI

## Evidence from the actual stock ELF

A read-only extraction of `lib/modules/mac80211.ko` from the previously uploaded `vendor_boot_a.img` produced SHA256 `f404b741cda2012557d567efec688148e7d4578e127b1de4f347e7f8f8445e87`, identical to previous recovery module inspection. The user separately verified that the running module's GNU Build-ID matches its preserved recovery copy.

Direct parsing of this ELF's `.BTF` metadata found:

- `struct ieee80211_ops`: **115 members**, **920 bytes** (all members at 8-byte intervals).
- The module-local member names contain **`testmode_cmd` (index 50)** and **`testmode_dump` (index 51)**, indicating the module's structure includes the callbacks gated by **`CONFIG_NL80211_TESTMODE`**.
- Nearby confirmed BTF names `sta_add` → `sta_remove` → `sta_notify` have **no `sta_add_debugfs`** callback, consistent with **`CONFIG_MAC80211_DEBUGFS=n`**.
- **98 names** resolve from the module's self-contained BTF string table; 17 reference a mismatched external base BTF and are intentionally marked unresolved.

In the pinned `include/net/mac80211.h` from Motorola public kernel commit `0fa176ca7f56c349b51acd83684284c02ced5854`, `testmode_cmd` and `testmode_dump` are conditionally compiled under `#ifdef CONFIG_NL80211_TESTMODE`. This configuration may differ from the Android **base kernel** `/proc/config.gz` because `mac80211.ko` was built and loaded separately.

## Purpose of PR

Previous experimental FullLTO build exported `ieee80211_alloc_hw_nm=0x55ebf907` with `CONFIG_MAC80211_DEBUGFS=n`, while the real stock `mac80211.ko` exports **`0x561b7fc2`**.

Instead of modifying CRC metadata, compile **only** `net/mac80211/main.o` under FullLTO twice from one verified public source and the verified original stock base config. Hold `CONFIG_MAC80211_DEBUGFS=n` constant and vary only:

1. **`CONFIG_NL80211_TESTMODE=n`**: no testmode callbacks.
2. **`CONFIG_NL80211_TESTMODE=y`**: the callback pair present in the actual stock BTF.

For each, CI records the resolved Kconfig, genksyms `main.symtypes` trace, compiler version and resulting CRC. No `.ko`, boot image, kernel source tree, signed module or installer is uploaded.

## Interpreting results

If `CONFIG_NL80211_TESTMODE=y` reproduces the stock CRC `0x561b7fc2`, we have recovered the **specific type-signature input** explaining the single previously identified wireless CRC mismatch. That would be a substantial **diagnostic** improvement, but we still **MUST NOT** load the AR9271 modules without proving all the kernel imports against actual live core KMI, `vermagic`, CFI, Android module signing, firmware paths, OTG enumeration and recovery safety.

If neither matches, other build source/config/header differences remain. A matching `ieee80211_ops` field count or size alone is not enough to prove a function type signature matches: its referenced types and structs matter.

**Safety:** This CI job is offline, read-only and non-installable. It will not modify your Motorola XT2615-1, KernelSU, TWRP, OrangeFox, PBRP, SHRP, or internal MediaTek Wi-Fi.
