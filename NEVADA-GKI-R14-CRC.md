# XT2615-1 Nevada — exact GKI r14 source fingerprint CRC probe

## Crucial source fingerprint

The user's running kernel release is `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`. Official Android `android13-5.15` archived release documentation maps **`android13-5.15-2025-05_r14`** (2025-12-11) to a commit whose SHA begins **`9b2308ac0ad6`**, an exact match to the running base kernel's Git suffix.

Official source: https://source.android.com/docs/core/architecture/kernel/gki-android13-5_15-deprecated-builds

**Limitation:** The running `mac80211.ko` has its own `5.15.180-android13-8-g6558a72298ed` vermagic. Thus, the r14 GKI commit may be the **base kernel** source without being the exact source used to build the separately loaded Wi-Fi module. The live module's Build-ID notes match the recovered recovery copies, which allows us to treat their exported `ieee80211_alloc_hw_nm` CRC `0x561b7fc2` as an authoritative reference.

## Why this test

Previous experiments showed:

- Successful LED-free Atheros AR9271 compilation with no missing LED imports.
- Experimental ThinLTO/FullLTO export `ieee80211_alloc_hw_nm` CRC `0x55ebf907`, **not equal** to the firmware reference.
- No-LTO export `0x856d772a`, also **not equal**.
- A May 2025 *moving branch* of public GKI matched the Motorola public source's type trace, but its HEAD did not identify the stock kernel's r14 source commit. Therefore, the exact **official release tag** is the more appropriate next candidate.

## CI-only experiment

This pull request adds a GitHub Actions workflow that:

1. Verifies the exact uploaded `ci/xt2615-nevada-stock.config` SHA256.
2. Fetches official Android `kernel/common` tag `android13-5.15-2025-05_r14` directly from Google's Gitiles, checks that its resolved commit starts with `9b2308ac0ad6` and that `make kernelversion` is `5.15.180`.
3. Reuses the existing `scripts/nevada-mac80211-lto-crc-matrix.sh` so this test stays comparable to the Motorola public-source experiment.
4. Compiles only `net/mac80211/main.o` in No-LTO, ThinLTO and FullLTO diagnostic modes.
5. Records exported CRCs, type-trace hashes and the difference from `0x561b7fc2`. Uploads **text evidence, not installable binaries**.

If the official Google repo or exact tag is inaccessible, the workflow must **fail safely** rather than substituting another source revision.

The user-provided stock config originally targets Android Clang **14.0.7 r450784e** with FullLTO. The CI uses Ubuntu Clang and disables the unavailable private `TRIM_UNUSED_KSYMS` whitelist. Enabling CFG80211 and MAC80211 as temporary modules is necessary for the test. These differences mean the output remains a **diagnostic probe**, never proof of installable kernel or driver compatibility.

## Interpreting the results

A matching CRC is encouraging but doesn't verify all imports, module CFI, vermagic, actual source commit of `mac80211.ko`, signature policy, OTG, USB device, and firmware. A mismatch narrows the next work to exact Wi-Fi module source provenance and vendor changes.

**Never install/flash experimental outputs, overwrite live Wi-Fi modules, forge CRCs, alter `vermagic`, or touch KernelSU/TWRP/OrangeFox partitions.**
