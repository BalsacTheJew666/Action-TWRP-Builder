# Nevada / XT2615-1 — public GKI 14563692 candidate export retention

**Research-only / not authoritative Motorola KMI / not a bootable kernel / do not flash.**

## On-device and official release observations

The actual Motorola Moto G Play (2026), Android 16 firmware \`W1WNS36.18-114-1\`, kernel \`5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692\`, was evaluated in normal boot:

- 181 authentic loaded stock vendor/module ELF files were read; 181 duplicated mount paths collapsed.
- **82/101 distinct** Atheros experimental core import CRC requirements corroborated via matching stock module imported \`__versions\`; no witness CRC conflicts. 19 names had no on-device imported-symbol witness (16 USB + \`rfkill_pause_polling\` + \`device_release_driver\` + \`kmemdup\`).
- Exact published Google GKI build **14563692**, the same base revision as the live kernel, had **8,471 distinct \`vmlinux\` exported symbols** in its \`vmlinux.symvers\`. Earlier audit matched 134/136 core-import instances, with only two symbols missing.
- The two outstanding kernel exports are \`usb_get_urb\` and \`rfkill_pause_polling\`. Both function names appear in the live kernel kallsyms but no respective \`__ksymtab\` names appeared, despite kallsyms displaying many other exports.
- The original stock \`.config\` SHA256 \`e3cdaf997a7e2eb70e441944bdfd9af359aa82e8a2d5cb9534d2bce5fcd4a78a\` enables \`CONFIG_TRIM_UNUSED_KSYMS\`, \`CONFIG_MODVERSIONS\`, \`CONFIG_CFI_CLANG\`, \`CONFIG_MODULE_SIG_PROTECT\`, \`CONFIG_LTO_CLANG_FULL\`, and references a missing build-time generated original \`abi_symbollist.raw\` at \`/mnt/disks/build-disk/src/android/common-android13-5.15-2025-05/out/android13-5.15/common/abi_symbollist.raw\`.

## What this next workflow does

1. Download ONLY the **exact immutable Google GKI 14563692** public \`vmlinux.symvers\`, parse its exported symbols and modversion CRCs, reject a table with an unexpected number of symbols or malformed records, and record the source SHA256.
2. Independently read the actual original 101-distinct-symbol Atheros core-import CRC manifest from PR #17; assert **99 of 101** have the **same CRC values** in official GKI. Reject unexpected discrepancies. Verify that the **only two missing names** are \`usb_get_urb\` and \`rfkill_pause_polling\`.
3. Form a **conservative candidate superset**: all 8,471 official GKI exports + those 2 = **8,473 names**, alphabetically sorted. This avoids losing any *known* baseline public GKI export to symbol trimming. It is *not* proof of coverage for additional Motorola/MediaTek vendor-only exports.
4. Fetch the commit-pinned public Motorola source, exercise its original \`scripts/gen_autoksyms.sh\` in a synthetic isolated workspace and assert all 8,473 retention macros appear. No custom kernel is compiled.
5. Save **text-only** whitelist candidate and JSON evidence to GitHub Actions. No proprietary \`.ko\`, firmware, boot or recovery image is uploaded. No device accessed.

Unlike the earlier two-symbol-only micro-test, this candidate retains **all published baseline exports**. But it is **still NOT the complete genuine Motorola vendor whitelist**.

## Why the candidate cannot be installed or flashed

The GKI \`vmlinux.symvers\` reports **what the published base kernel actually exported**. An original \`abi_symbollist.raw\` is a **build-time allowed retention set** which may include symbols for drivers that were not present in the public GKI output, and a Motorola-modified build may contain additional exports. Therefore: published names are useful for avoiding baseline regressions, but **they do not prove the original vendor ABI is completely reconstructed**.

Outstanding gates before a serious compatible custom GKI build:

- Recover or safely independently reconstruct and verify **all exports needed by the phone's vendor modules**, not just the 101 Atheros imports. The original private \`abi_symbollist.raw\` is still absent.
- Use a matching and reproducible Android-Clang toolchain, full original Kconfig, correct official Motorola source/patch integration and original DTB/vendor/module interface, not a generic Ubuntu Clang approximation.
- Address \`CONFIG_MODULE_SIG_PROTECT\`, signing keys, Clang CFI/full LTO and exact target module \`vermagic\` without patching CRCs or bypassing security.
- Independently protect the user's working KernelSU Next root state, internal MediaTek Wi-Fi, boot/AVB and all existing recoveries before any device-side experiment.
- External AR9271 USB adapter is not available for functional testing yet, so no OTG, firmware, monitor mode or injection claims are appropriate.

## Next safe gate after this result

Use only a **read-only stock-vendor symbol import inventory** to identify vendor-specific symbols not included in the exact public GKI exported set, then compare those imports with the candidate list. Any extra required vendor export missing from public GKI must be addressed before a full custom kernel build. Do not upload proprietary module binaries to public CI.

## References

- Exact official build: https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers
- Official Android GKI release artifacts: https://source.android.com/docs/core/architecture/kernel/gki-android13-5_15-release-builds
- Android kernel symbol list workflow: https://source.android.com/docs/core/architecture/kernel/howto-symbol-lists
- Preceding safe two-export test: https://github.com/BalsacTheJew666/Action-TWRP-Builder/pull/23

**Never use this candidate symbol list as the sole KMI input to build a flashable image.**
