# Motorola XT2615-1 — Stock Wi-Fi / Atheros ELF CRC preflight

## Why

Earlier CI experiments repeatedly failed to reproduce stock `mac80211.ko`'s exported `ieee80211_alloc_hw_nm` CRC **`0x561b7fc2`** (experimental `ath9k_htc.ko` imports **`0x55ebf907`**). The module's `scmversion=g6558a72298ed` does not resolve using validated short-SHA lookups on Google's public `kernel/common` repository. We need an actual binary-to-binary import comparison, not another speculative compilation.

## New read-only audit completed offline

Preserved stock recovery copies from the user's uploaded `vendor_boot_a.img` were extracted without changing the device. Their SHA256 checksums:

- `mac80211.ko`: `f404b741cda2012557d567efec688148e7d4578e127b1de4f347e7f8f8445e87`
- `cfg80211.ko`: `85f877d3866f0668fea72a725e1506fd0979d9e636e94e69c0f3328f917dcb90`

The running stock modules' GNU Build-ID values were separately checked on the handset in prior read-only diagnostics and matched the recovered modules. This validates their identity, **not** the source revision or every loader requirement.

Compared with experiment artifact `nevada-stockconfig-ar9271-abi.zip` (run #40177303389), four experimental driver modules `ath.ko`, `ath9k_hw.ko`, `ath9k_common.ko`, `ath9k_htc.ko` contain **233** imported modversion entries in total.

| Category | Imported symbol instances |
| --- | ---: |
| Match actual stock `mac80211.ko` or `cfg80211.ko` ELF export CRC | 29 |
| Mismatch against actual stock Wi-Fi framework CRC | **1** |
| Match other experimental Atheros module export CRC | 67 |
| Match **experimental** GKI `vmlinux.symvers` CRC | 136 |
| Unresolved among these providers | 0 |

**Only verified mismatch against the saved stock wireless modules:** `ath9k_htc.ko` import `ieee80211_alloc_hw_nm`, which requests `0x55ebf907` but stock `mac80211.ko` exports `0x561b7fc2`.

The repository includes **only** a plaintext 30-import Wi-Fi CRC snapshot and an offline Python analyzer, not proprietary `.ko` binary files. The 30-entry snapshot has 29 matches and the single mismatch. The separate 136 core CRC checks are against a **candidate core kernel build**, not authoritative on-device `Module.symvers`. The 67 Atheros mutual matches are against one another **within the same experimental archive**. Therefore these results narrow the known Wi-Fi blocker but do NOT establish full KMI, CFI, signature, or load-time compatibility.

## Reproduce locally from preserved source files

Run with `readelf` installed:

```sh
python3 scripts/nevada-ar9271-stock-elf-preflight.py \
  /path/to/stock-mac80211.ko \
  /path/to/stock-cfg80211.ko \
  /path/to/nevada-stockconfig-ar9271-abi.zip \
  nevada-ar9271-abi-report.json
```

The analyzer verifies stock module SHA256 checksums, parses ELF absolute `__crc_*` exports and 64-byte `__versions` import entries, correlates Atheros module-to-module versions, then marks tentative candidate-core checks separately.

The PR workflow tests parser logic and the sanitized 30-symbol snapshot **only** because raw stock modules are not in GitHub. A CI green check is not a fresh device audit and not a compatible build.

## BTF limitation

The recovered `mac80211.ko` contains a split `.BTF` section. A preliminary attempt to resolve it using base BTF extracted from the saved boot image failed because the referenced type IDs could not be reconciled. This does **not** prove the BTF is malformed or reveal a specific structure-layout mismatch. Until the matching module build's original base BTF is known, avoid treating split BTF as a verified source of precise C type layout differences.

## Next engineering gate

Find the original `mac80211` source or a non-spoofed compilation configuration that reproduces its true `ieee80211_alloc_hw_nm` ABI. Then check all new Atheros symbols against authoritative actual live core/stock module exports, compiler, CFI, `vermagic`, firmware availability and USB adapter enumeration.

**Do not fake module CRCs, force insmod, replace stock Wi-Fi modules, flash boot images or risk working KernelSU/TWRP/OrangeFox.** This is an audit artifact only.
