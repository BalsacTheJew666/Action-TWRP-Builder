# Nevada XT2615-1: private 264 owner-tag to on-disk ELF CRC crosscheck

## Live device finding

The read-only 264-name triage reported 264/264 symbols tagged to owners loaded in /proc/modules, with 11,772 visible __ksymtab_* entries in /proc/kallsyms. The two AR9271 critical symbols, usb_get_urb and rfkill_pause_polling, still have no visible __ksymtab_* export entries.

These 264 names are evidenced as module-owned exports, not unambiguously core kernel vmlinux exports. A live owner tag does not prove the exported modversion CRC.

## New on-device research gate

- Reads existing local private reports private-264-unresolved-export-triage.json and private-module-providers.json. Rejects inconsistent or non-264/1006 report inputs.
- Matches the 264 imported symbol names to the tagged, presently loaded kernel modules, using root-only read commands when needed.
- Discovers matching on-disk stock module ELF candidates. Refuses nonidentical module files with the same name.
- Parses declared __ksymtab_* and optional absolute __crc_* ELF symbols, comparing any available CRC with the original importer requirement.
- Distinguishes available CRC matches, conflicts, absent/stripped CRC values, and missing/ambiguous disk module files. Disk candidate metadata is NOT an authenticated live kernel CRC or exact loaded binary proof.
- Writes only a private 0600 JSON under Termux, and only aggregate totals to stdout.
- Does not install, flash, insmod, patch symbol CRCs, alter module load policy, change KernelSU, touch recovery, or upload any device binaries.

## Termux run (after CI regression test)

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-264-owner-elf-private-crc-gate.py?ref=nevada-264-owner-disk-elf-private-crc-crosscheck" \
  > private-264-owner-gate.py.new || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-vendor-export-provider-local.py?ref=main" \
  > private-elf-parser.py.new || exit 1

python -m py_compile private-264-owner-gate.py.new private-elf-parser.py.new || exit 1
mv private-264-owner-gate.py.new private-264-owner-gate.py || exit 1
mv private-elf-parser.py.new private-elf-parser.py || exit 1
set -o pipefail

python private-264-owner-gate.py \
  --triage-report private-264-unresolved-export-triage.json \
  --provider-report private-module-providers.json \
  --witness-script witness.py \
  --elf-parser-script private-elf-parser.py \
  --report private-264-owner-elf-crc.json \
  | tee private-264-owner-elf-summary.txt
~~~

Share only the console summary, not full private files.

## Limits

The 264 owner-tagged symbols should NOT be appended en masse to vmlinux's KMI whitelist. Neither original stock vendor ABI symbollist.raw nor all vendor requirements have been fully reconstructed. Two important AR9271 kernel exports remain absent in the original running kernel. Exact FullLTO/compiler, modversions, CFI, signing, vermagic and KernelSU compatibility remain separate gates. NO FLASH/INSMOD.
