# XT2615-1 Nevada — public GKI 14563692 export superset for AR9271 (RESEARCH ONLY)

## The previous results, from actual device and exact release

- Stock \`mac80211.ko\` and \`cfg80211.ko\` references: **30/30** Atheros imported CRC values matched.
- Four experimental Atheros modules imported **233** symbols total: 30 saved stock Wi-Fi, 67 between experimental Atheros modules and 136 core kernel import *instances*.
- Google Android GKI \`kernel_aarch64\` official build **14563692** \`vmlinux.symvers\` matched **134/136** core imports. The only missing exported names were \`rfkill_pause_polling\` and \`usb_get_urb\`.
- Read-only on-device user audit collected 181 valid already-loaded stock-module ELF files; corroborated **82/101** *unique* Atheros core symbol CRC requirements with **zero conflicts**. The remaining 19 had no matching live-module import *witness*, not 19 proven CRC incompatibilities. Seventeen of those 19 matched the official GKI table; two did not.
- Root-visible kallsyms function names \`usb_get_urb\`, \`rfkill_pause_polling\` exist, but \`__ksymtab_...\` entries for both were not seen, even though other \`__ksymtab_\` entries were visible.
- The stock Kconfig has \`CONFIG_TRIM_UNUSED_KSYMS=y\` and points to a **non-public** Motorola/GKI \`abi_symbollist.raw\`, which has **not** been recovered.

## Precisely what the new CI reconstructs

This is **not** an authentic Motorola KMI symbol list. The public workflow:

1. Fetches official \`vmlinux.symvers\` from **Google GKI kernel_aarch64 build 14563692**, not experimental compiler output. Rejects malformed files or an export count outside the independently observed public release range.
2. Extracts **all exported \`vmlinux\` names** into a deterministic sorted set, without overriding any CRC value.
3. Checks each of the **101 actual AR9271 core import requirements** (from the previously saved sanitized ELF manifest) against the official GKI exported CRC values. Fails on any conflict or unexpected missing name, including if the two known blockers appear unexpectedly.
4. Adds exactly **two public source-proven \`EXPORT_SYMBOL\` names**: \`usb_get_urb\` and \`rfkill_pause_polling\`.
5. Uses the real \`scripts/gen_autoksyms.sh\` from SHA-pinned public Motorola \`kernel-mtk\` to show the complete generated \`__KSYM_...\` macro list includes the official public exports plus the two additions.
6. Uploads only **textual** provenance, JSON, name-only symbol list and generated include. Never builds/patches/signs a kernel or touches the phone.

The result is a **PUBLIC GKI export-name superset**, useful for an offline build-scoping experiment. It protects against the catastrophic previous idea of compiling with an allowlist of only two names.

## Why this cannot be used as a flash-safe stock-kernel whitelist

The exact original \`CONFIG_UNUSED_KSYMS_WHITELIST\` points to an unavailable absolute path inside Motorola's Android build environment. This public superset cannot establish whether **additional vendor-specific exports** or module dependencies beyond official GKI belong on that original list. It does not include proprietary firmware, proprietary vendor ELF modules or root state.

Keeping public GKI export *names* also does not establish that a custom GKI build will produce the exact **CRC, CFI metadata, vermagic, compiler output or vendor module compatibility**. The stock \`CONFIG_LTO_CLANG_FULL=y\` used Android Clang r450784e, while previous experimental AR9271 builds used Ubuntu Clang and ThinLTO. The original stock also enables \`CONFIG_MODULE_SIG_PROTECT=y\`; \`CONFIG_MODULE_SIG_FORCE=n\` does not by itself settle on-device signature policy.

The script therefore names every output \`NOT-VENDOR-COMPLETE\` or \`NEVER-FLASH\`. CI success means **only** that the publicly documented export universe and additions were generated consistently.

## Correct next kernel-build gate

Before building any device-specific installable image, obtain genuine vendor-specific export coverage (for example from authenticated stock \`vmlinux.symvers\`, a full matching Motorola ABI whitelist, or an audit of all original stock module imports and exports) and verify against the **full** list of stock modules. Validate the generated kernel's matching \`kernelrelease\`, actual compiler/toolchain, ELF/modversions, module signing and CFI plus KernelSU compatibility in separate diagnostic-only steps.

No existing TWRP/OrangeFox/PBRP/SHRP build, KernelSU Next installation, live Wi-Fi, recovery image or boot partition is modified by this stage.

## Sources of inputs

- Pinned Motorola kernel source: \`MotorolaMobilityLLC/kernel-mtk\`, commit \`0fa176ca7f56c349b51acd83684284c02ced5854\`.
- Official Google public GKI exported CRC table: \`https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers\`.
- Sanitized stock Kconfig SHA256: \`e3cdaf997a7e2eb70e441944bdfd9af359aa82e8a2d5cb9534d2bce5fcd4a78a\`, committed as \`ci/xt2615-nevada-stock.config\`.
- Sanitized AR9271 core import CRC table: \`ci/nevada-ar9271-core-kmi.tsv\`, previously derived from the four experimental Atheros \`.ko\` files.
