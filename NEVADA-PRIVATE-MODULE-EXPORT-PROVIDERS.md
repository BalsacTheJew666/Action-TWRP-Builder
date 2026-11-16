# XT2615-1 Nevada — classify private vendor import providers without disclosing device files

## Verified phone and compiler results (October 27, 2026)

The user ran the PRIVATE local vendor import inventory on rooted Motorola nevada, kernel 5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692:

- Already-loaded stock module ELFs read: **181 / 358** names in /proc/modules.
- Distinct imported symbol names: **2,472**.
- Match official Google GKI **14563692** vmlinux.symvers: **1,466** names.
- Imported names **not in public GKI vmlinux**: **1,006**, no same-name CRC conflicts against official GKI exports.
- AR9271 core witnesses: **82 matching / 101**, zero conflicts, 19 without a stock import witness.
- Two AR9271 core blockers: usb_get_urb and rfkill_pause_polling, missing from official GKI and not visible as device __ksymtab_ entries.

The separate build-only experiment **#40481454888** compiled an isolated research kernel with the 8,473-name public export list and found both missing exports genuinely retained, matching its experimental ath9k_htc.ko CRCs. This does not establish vendor ABI, bootability, root or installability.

## Why 1,006 is NOT the number of missing kernel exports

Stock drivers import symbols from **other loaded vendor modules** (such as wireless framework and MTK vendor components). A name absent from Google's vmlinux.symvers might be exported by a vendor module. We cannot automatically put all 1,006 names into the kernel retention whitelist or claim we've recovered Motorola's unavailable private abi_symbollist.raw.

This next test indexes the **exporting** stock module ELFs, not only their imports.

## New private provider audit

The new Python script `scripts/nevada-vendor-export-provider-local.py` runs locally with the already saved `vendor-private-kmi-inventory.json`. It:

1. Uses the existing audited read-only witness helper to find already-loaded .ko files, collapse Android mount aliases, and reject differing or unreadable candidates.
2. Reads each ELF64 symbol table and checks for **defined** `__ksymtab_SYMBOL` declarations. When exported CRCs exist as absolute `__crc_SYMBOL` symbols, compares those with the imported stock module CRCs. A matching string in `__ksymtab_strings` without a defined symbol is **weak evidence only**.
3. Counts how many public-GKI-absent import names have one or more declared loaded-module providers, only weak evidence, or no visible provider among the scanned modules.
4. Prints only aggregate counts. Saves detailed JSON in Termux as private mode 0600; does not upload private files.
5. Is tested in public GitHub Actions ONLY on synthesized ELF files. No device, real vendor module, boot image or private report enters CI.

**Important:** An on-disk ELF may not be authenticated against a live loaded module's exact build. We scanned only 181 of 358 currently loaded module names. Missing providers may reside in the other 177, or in built-in/vendor kernel exports. Do not label unrecognized symbols as vmlinux exports or add them to a KMI whitelist.

## Termux commands (READ ONLY)

Run from the Termux workspace that already has `vendor-private-kmi-inventory.json` and the current `witness.py`:

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-vendor-export-provider-local.py?ref=nevada-private-vendor-module-export-providers" \
  > provider-audit.py.new || exit 1

python -m py_compile provider-audit.py.new || exit 1
mv provider-audit.py.new provider-audit.py || exit 1

set -o pipefail
python provider-audit.py \
  --inventory-json vendor-private-kmi-inventory.json \
  --witness-script witness.py \
  --report private-module-providers.json \
  | tee private-module-providers-summary.txt
~~~

Share **only the printed aggregate console summary** beginning with "MOTOROLA NEVADA PRIVATE MODULE-EXPORT PROVIDER AUDIT". Keep JSON and original stock .ko files and firmware private.

## Interpret the output safely

- `one_loaded_module_ELF_declaration`: evidence a readable loaded-module *file* declares the export, not that kernel vmlinux exports it.
- `multiple_loaded_module_ELF_declarations`: ambiguous, no provider assumed.
- `only_ksymtab_strings_candidate`: weak evidence, especially when .symtab stripped.
- `no_provider_seen_among_readable_loaded_modules`: unknown, NOT a confirmed missing kernel export; also consider the 177 loaded names without an ELF file.
- `available_export_crc_comparisons_conflicting > 0`: investigate before any kernel candidate. Never spoof import CRCs or rewrite loader checks.

**NO installation, insmod or flashing**. The phone's KernelSU Next, recoveries, internal Wi-Fi, SELinux and kernel are unchanged.
