# XT2615-1 Nevada: test the optional mac80211 debugfs callback against stock CRC

## Why this follows the stock ELF audit

The previous experimental AR9271 modules have **29 matching stock Wi-Fi import CRCs** and **one mismatch**: `ieee80211_alloc_hw_nm` is required at `0x55ebf907` while live stock `mac80211.ko` exports `0x561b7fc2`. This does **not** establish that all kernel imports are compatible.

We examined the stock Wi-Fi module's actual ELF `.BTF` bytes:

- Original stock `mac80211.ko` SHA256: `f404b741cda2012557d567efec688148e7d4578e127b1de4f347e7f8f8445e87`
- Struct `ieee80211_ops` is **920 bytes** with **115 members**.
- Module-local BTF names reliably show `sta_add` (index 31), `sta_remove` (32), immediately followed by `sta_notify` (33): **no `sta_add_debugfs` member**.
- In the pinned public `include/net/mac80211.h`, the optional `sta_add_debugfs` callback is wrapped by `#ifdef CONFIG_MAC80211_DEBUGFS`. This is a plausible build-config difference, not proof of changed source.
- The stock module was compiled using Android Clang 14.0.7 r450784e. Our CI uses Ubuntu Clang and lacks Motorola's private symbol whitelist.

### Why older split BTF decoding failed

The module's own BTF local string-offset base resolves to **2390229**, whereas the extracted boot-image base BTF string table is **2393441** bytes. Names from the module-local string table can be decoded; **names that reference the mismatched external base are not trustworthy**. We have **not** recovered the complete authentic type graph or function signature. In particular, do not treat guessed names on external-base-only fields as confirmed.

## Targeted CI experiment (no flashable)

PR adds a FullLTO-only test on the same pinned public Motorola commit `0fa176ca7f56c349b51acd83684284c02ced5854` and verified stock base configuration. It compiles only `net/mac80211/main.o` twice, varying precisely `CONFIG_MAC80211_DEBUGFS`:

1. `MAC80211_DEBUGFS=n`: expects optional callback absent; saves resolved Kconfig, generated type trace and exported CRC.
2. `MAC80211_DEBUGFS=y`: includes callback; saves identical evidence.
3. Compares both CRCs against the actual stock export `0x561b7fc2`.

This should establish whether the optional callback is responsible for a CRC change under the compiler used in CI. A match on one CRC would still require proving the module's actual type graph, compiler KMI, *all* symbol versions, vermagic, CFI and load-time policy before driver installation. If both miss, stop pursuing this particular flag and investigate other source/config differences.

## Safety

This is offline read-only analysis. No uploaded stock binaries are committed to GitHub; only small sanitized BTF evidence, scripts, resolved configs and diagnostics. No `.ko` is published, no CRCs/version strings are overwritten, no `insmod`, no flash. Preserve working KernelSU, TWRP, OrangeFox, SHRP/PBRP and internal Wi-Fi.
