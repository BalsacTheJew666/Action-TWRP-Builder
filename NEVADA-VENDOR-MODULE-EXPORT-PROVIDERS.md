# XT2615-1 — Identify module exporters for non-public GKI stock import names (PRIVATE)

## Why

The real Motorola XT2615-1 (nevada), normal-boot Android 16 GKI build \`14563692\`, successfully read **196** original stock module ELF \`__versions\` files from **392** .ko paths (196 mount aliases collapsed). The private local stock-module imported-symbol inventory reported:

- 2,613 distinct imported symbol names, with 2,613 imported symbol/CRC pairs (no duplicate requirements with different CRCs).
- 1,494 unique stock imports match Google's official public \`vmlinux.symvers\` CRCs exactly.
- 1,119 names are **not in the official public GKI table**; 1,635 import entries refer to those names. Examples include ISP, KREE secure-memory, MediaTek GPU QoS, cfg80211 and vendor tracepoint symbols.

**The 1,119 unknown names are not 1,119 necessarily missing vmlinux exports.** Most can legitimately come from other loadable modules. The full original Motorola \`abi_symbollist.raw\` is still missing. Blindly appending all 1,119 imported names to a kernel KMI retention list would be incorrect.

Separately, experimental research-only kernel+AR9271 driver CI #40481454888 succeeded with public GKI 8,473 symbol names and both candidate core exports compiling with identical import CRCs:

- \`usb_get_urb\`: \`0x3c85197c\` in experimental vmlinux and ath9k_htc;
- \`rfkill_pause_polling\`: \`0x3939f8f0\` likewise;
- 30/30 previously captured stock Wi-Fi module CRC reference matches.

That compiler result is NOT approval to install anything: the true live Motorola kernel still does not show either targeted \`__ksymtab_*\` and the original vendor export whitelist, exact Clang/CFI/module signature policy, device kernelrelease and KernelSU remain unverified.

## What this private scanner actually does

The \`scripts/nevada-vendor-module-export-attribution.py\` tool accepts your local \`nevada-stock-vendor-kmi-report.json\`, uses the verified read-only helpers from \`nevada-stock-vendor-kmi-import-inventory.py\` and \`nevada-ar9271-live-core-kmi-witness.py\`, and collects only locally:

1. Search system/vendor \`.ko\` files on the phone (root \`find\` and \`cat\` are read-only when needed).
2. Reject differing binaries with the same module name, and collapse mount-path aliases.
3. Inspect ELF \`__ksymtab_strings\` for candidate exported symbol names. Some stock modules may have no readable export string table; lack of one is inconclusive.
4. Attribute imported non-public-GKI names to one or more *possible* stock module ELF providers, without pretending their CRCs have been checked.
5. For names not accounted for by those sections, cross-check root-visible \`/proc/kallsyms\` for \`__ksymtab_\` names, **never saving kernel memory addresses**. The presence of a kallsyms export name alone does not identify whether it's from vmlinux or a loaded module.
6. Keep the full symbol-level metadata **private in Termux**, with JSON file permissions \`0600\`. Print only aggregate counts and the two outstanding AR9271 blocker names.

This identifies likely module-to-module dependencies while avoiding unsupported KMI assumptions. The CI tests use only **synthetic ELF files** with fabricated exported names, and never access private Motorola data.

## Run read-only on the rooted Motorola from Termux

The following assumes your previous inventory was saved in \`$HOME/nevada-live-kmi/nevada-stock-vendor-kmi-report.json\` and the two earlier scripts are present.

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-vendor-module-export-attribution.py?ref=nevada-vendor-module-provider-attribution" \
  > export-providers.py.new || exit 1

python -m py_compile export-providers.py.new || exit 1
mv export-providers.py.new export-providers.py || exit 1

set -o pipefail
python export-providers.py \
  --stock-import-report nevada-stock-vendor-kmi-report.json \
  --stock-inventory-script nevada-stock-vendor-kmi-import-inventory.py \
  --output nevada-private-export-provider-report.json \
  | tee nevada-export-provider-summary.txt
~~~

Share only the **aggregate console summary** from \`nevada-export-provider-summary.txt\`. The full JSON includes symbol/provider metadata and stays local.

### Interpretation

- A match under \`possible_module_export_providers\` means a candidate module ELF contains that exported name. It does **NOT** verify that loaded module's **export CRC**, exact memory-loaded file version or the running kernel's core export status.
- \`non_public_import_name_visible_in_live_ksymtab_but_not_candidate_modules\` describes export names visible in the running kernel symbol table that weren't matched to one of the available stock module export sections. It is not proof they are built into vmlinux.
- \`not_yet_attributed_symbol_names\` may be in unloaded/missing modules, built-in vendor kernel code or trimmed/nonexported functions. Never mark them as compatible without more evidence.

No module load, custom kernel flashing, recovery, KernelSU Next, internal Wi-Fi, private firmware or bootloader state is modified.
