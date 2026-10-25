# XT2615-1 Nevada — KMI preflight (experimental, non-flashable)

## Motivation

The user-verified Motorola firmware `W1WNS36.18-114-1` has:
- Linux kernel `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`;
- A working KernelSU **LKM** loader inside `init_boot_a`;
- Working TWRP in the **recovery ramdisk** of `vendor_boot_a`;
- Loaded `cfg80211` and `mac80211` from independently built modules;
- A stock `/proc/config.gz` where `CONFIG_CFG80211` is **not set**.
  This is consistent with separate wireless modules and does *not* imply
  cfg80211 is unavailable at runtime.

The first public experimental NetHunter build forcibly set
`CONFIG_CFG80211=y` and `CONFIG_MAC80211=y`, potentially conflicting with
Motorola's stock module arrangement. It also used Ubuntu Clang 14.0.0 and
ThinLTO, while the stock kernel used Android Clang 14.0.7 (r450784e)
and Full LTO. **Successful compilation did not establish ABI compatibility.**

## This CI experiment

Workflow: `.github/workflows/XT2615-Nevada-KMI-Preflight.yml`

1. Checks out exactly pinned public Motorola source commit
   `0fa176ca7f56c349b51acd83684284c02ced5854`.
2. Uses public-source GKI defconfig, retains cfg80211/mac80211 as absent
   **in the core kernel**, retaining the vendor-modular design.
3. Uses memory-saving ThinLTO + CFI for *diagnostic CI only*.
4. Builds a compressed Image for symbol generation, but uploads only
   `vmlinux.symvers`, optional `Module.symvers` (if produced), generated
   Kconfig, hashes, and a textual report.
5. Uploads a build log even on normal compilation failure.

It **never** downloads stock boot images, stock modules, proprietary firmware,
TWRP ramdisks, or KernelSU. It has **no flashing commands** and no secret
or cross-repository token permissions.

## How to run

After the PR is reviewed and merged:
- Open **Actions → XT2615-1 Nevada - KMI Preflight (Non-flashable)**.
- Select `main` and manually dispatch.
- Download `nevada-kmi-preflight-NOT-FLASHABLE` from the run's artifacts.
- Compare candidate `vmlinux.symvers` CRCs against module `__versions`
  from the firmware-matched Motorola `cfg80211.ko`, `mac80211.ko`,
  and other vendor modules **outside public GitHub**.
- Record missing and mismatched exports before attempting an external USB
  Wi-Fi module, patch application, or candidate boot image.

**Caveat:** Passing this preflight cannot prove stock ABI. GKI config,
compiler, ThinLTO, trimming of exported symbols, localversion, and
vendor sources must be matched for a boot candidate. No Android boot or
vendor partition should be modified based on its output.

Kali patch guide:
https://www.kali.org/docs/nethunter/nethunter-kernel-1-patching/

Android KMI symbol CRC background:
https://source.android.com/docs/core/architecture/kernel/abi-monitor
