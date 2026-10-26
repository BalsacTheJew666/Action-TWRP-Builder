# Motorola XT2615-1 — source provenance of stock mac80211.ko

## What we know

- Working Android kernel: `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`.
- Running `mac80211.ko` and `cfg80211.ko` ELF Build-ID notes match modules recovered from the uploaded TWRP recovery image.
- `mac80211.ko` has `5.15.180-android13-8-g6558a72298ed` vermagic, **different** from the main kernel Git suffix.
- The stock Wi-Fi module exports `ieee80211_alloc_hw_nm` CRC **`0x561b7fc2`**.
- Our prior public Motorola/GKI-source AR9271 experiments produce **`0x55ebf907`** with either ThinLTO or FullLTO, and **`0x856d772a`** without LTO.
- The main kernel source was conclusively pinned to official Android GKI tag `android13-5.15-2025-05_r14` at `9b2308ac0ad616788fb57ba688aa07f0ff221355`. That source still did not reproduce the **separate wireless module** export CRC.

## Next step in this PR

Attempt to resolve `6558a72298ed` directly in the **official Android common-kernel Gitiles repository**, then fetch that exact verified commit from Google. The GitHub mirror did not expose that SHA via its commit endpoint, which by itself is not definitive evidence the commit is absent from Google's authoritative repository.

1. Request `https://android.googlesource.com/kernel/common/+/6558a72298ed?format=JSON`.
2. Reject any response whose 40-character commit ID does not start with `6558a72298ed`.
3. Attempt a shallow fetch for the verified exact 40-character commit, and verify that `make kernelversion` reports 5.15.180.
4. **Only when the exact commit is verified:** use the existing CI script to compile `net/mac80211/main.o` under No-LTO/ThinLTO/FullLTO; compare generated CRCs against `0x561b7fc2`.
5. **If exact source is missing or cannot be fetched:** record `SOURCE_NOT_VERIFIED` in the artifact and do not compile from substitute source.

Gitiles' ability to resolve abbreviated Git IDs or allow fetch-by-hash is uncertain. A failed lookup does not prove Motorola's module was never built from that source; it means the source is not verified through this method.


## Static evidence rechecked from preserved recovery binaries (Oct 26, 2026)

- Both stock `mac80211.ko` and `cfg80211.ko` contain **`scmversion=g6558a72298ed`** within their actual ELF `.modinfo` section; this is not merely a user-entered kernel version.
- The stock `mac80211.ko` `.comment` section identifies **Android (8508608, based on r450784e) Clang 14.0.7**, exact LLVM source `4c603efb0cca074e9238af8b4106c30add4418f6`.
- Recovered stock `mac80211.ko` GNU Build-ID: **`a1e463aa49179d3da609f3d73f45e753292fad59`**; SHA256 **`f404b741cda2012557d567efec688148e7d4578e127b1de4f347e7f8f8445e87`**. Recovered stock `cfg80211.ko` SHA256: **`85f877d3866f0668fea72a725e1506fd0979d9e636e94e69c0f3328f917dcb90`**.
- The initial CI attempt #40274035814 yielded HTTP 404 for short SHA `6558a72298ed`, and correctly skipped CRC compilation. A later control was added to test whether **known** source SHA `9b2308ac0ad6` resolves through the same Gitiles short-SHA method. Until that positive control is checked, the earlier HTTP 404 must **not** be interpreted as proof the requested commit is missing.

## Safety and interpretation

- Read-only CI research; no phone scripts, `.ko` packages, boot images, flash, or module loading.
- If Google resolves the SHA, that identifies a **source candidate** for the independently built Wi-Fi module; it does not by itself reproduce the original compiler, config, symbol whitelist, or ABI.
- Even a matching single symbol CRC does not prove all imports, CFI, signatures, firmware, USB enumeration, or NetHunter functionality are compatible.
- Never forge symbol CRCs, modify `vermagic`, replace stock `cfg80211` or `mac80211`, or risk current KernelSU, TWRP and internal Wi-Fi.
