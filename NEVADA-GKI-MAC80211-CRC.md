# XT2615-1 nevada — compare GKI 5.15.180 vs Motorola mac80211 exported CRC

## Established results

- XT2615-1 running kernel: `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`.
- Live `cfg80211` and `mac80211` Build-ID note hashes match copies recovered from the uploaded TWRP recovery image.
- These recovered modules have `5.15.180-android13-8-g6558a72298ed` vermagic, even though the running Motorola kernel has a different release string.
- The recovered `mac80211.ko` exports `ieee80211_alloc_hw_nm` CRC `0x561b7fc2`.
- The experimental LED-free `ath9k_htc.ko` imports `0x55ebf907`. Its two missing LED imports were eliminated.
- A stock-config-based Motorola build still produced `0x55ebf907`, and Motorola source's GKI vs stock Kconfig genksyms traces were byte-identical.

## New hypothesis

The existing compiled test uses Motorola's public MTK kernel tree. The actual loaded `mac80211` module has a **different GKI-style kernel release** that may reflect a separate Android common-kernel source revision. The base Linux version matches Android's May 2025 `android13-5.15` GKI branch. However, `g6558a72298ed` has **not** been verified as the exact published branch commit. Do not assume that any GKI 5.15.180 source is stock-matched merely from a similar release string.

An offline check of the user-provided `boot_a.img` also found valid kernel BTF; the recovered `mac80211.ko` has split module BTF. libbpf rejected that module BTF when using the boot image's BTF as the base, further evidence that the module BTF and main kernel may not be built against the same exact BTF identity. This is not proof that runtime modules are broken; the phone loads them, and its stock config permits some module BTF mismatch.

## This PR

Build **only** `net/mac80211/main.o` from two pinned public sources using identical diagnostic flags (Ubuntu Clang, GKI config, `MODVERSIONS=y`, `CFG80211=m`, `MAC80211=m`, ThinLTO):

- Motorola: `MotorolaMobilityLLC/kernel-mtk`, `android-16-release-w1wn36.18-114` at `0fa176ca7f56c349b51acd83684284c02ced5854`.
- Android common kernel: `aosp-mirror/kernel_common`, `android13-5.15-2025-05` at `5ee07dba9703de3e2c823100eba29f34df13cdc2`.

For each, read `__crc_ieee80211_alloc_hw_nm` directly from `main.o` as calculated by the kernel's own `genksyms`. Compare against firmware reference `0x561b7fc2`. Publish the `genksyms` type traces and source header diffs to isolate relevant differences.

**Possible findings:**
- GKI CRC matches reference and Motorola CRC does not: promising evidence to attempt a separate driver compile against the GKI source, followed by full CRC and module version checks. Never treat it as permission to install.
- Both differ: investigate a third vendor/partner source or a different GKI revision; never forge CRCs.
- Both match: analyze whether the earlier Atheros build used different configs/toolchain/type declarations and rerun comprehensive ABI checks.

## Safety and limits

- This job produces no `.ko` packages, no boot images and no fastboot/recovery instructions.
- It does not upload the user's boot image, module binary or private BTF.
- GKI May 2025 is a **research candidate**, not a verified exact Motorola firmware source.
- No scripts run on the phone. Preserve working TWRP, OrangeFox, KernelSU and internal MediaTek Wi-Fi.
- Even a symbol CRC match alone does not establish vermagic, signatures, CFI/LTO, all imported CRCs, or safe module loading.

Source context: Android `android13-5.15` May 2025 kernel version listings in official AOSP kernel release documentation.
