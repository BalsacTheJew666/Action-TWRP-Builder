# XT2615-1 Nevada — Validate AR9271 core imports from normal-boot modules

## Why this matters

PR #15 / GitHub Actions run #40413637325 compiled four Atheros modules and verified **30/30 stock Wi-Fi CRC imports**. Another **67** Atheros helper imports were consistent with the same experimental build.

There remain **136 kernel-core import instances**, representing **101 distinct core symbols**, which match only the *experimental* vmlinux.symvers table—not the actual phone's running kernel.

We independently analyzed the module __versions records from the user's preserved recovery vendor_boot_a.img, without changing the phone. The 212 recovered ELF modules corroborated **83 of the 101 distinct candidate core CRCs** with **zero conflicts** and 2,759 matching imported-symbol witness records. **18** distinct symbols lacked recovery evidence: device_release_driver, rfkill_pause_polling and **16 USB functions** (including usb_submit_urb and usb_register_driver).

These are **requirements recorded inside recovered modules**, NOT exports verified against the live kernel. Normal Android boot requires separate verification.

## Additional official GKI test completed before the device audit

PR #16, GitHub Actions run **#40437647125**, fetched the authoritative Google GKI build **14563692** symbol CRC export table for release `android13-5.15-2025-05_r14` (matching running base source commit `9b2308ac0ad616788fb57ba688aa07f0ff221355`). It compared all **233 actual imports** from corrected PR #15 Atheros modules and found:

- **30** matches with the saved stock Wi-Fi exports
- **67** matches with experimental Atheros helper modules
- **134 of 136 core import instances** matching official GKI export CRCs
- **2 required core symbols not exported by the official GKI reference:** `rfkill_pause_polling` and `usb_get_urb`

These two missing exports, not the earlier 18 missing *recovery witnesses*, are now the highest-priority actual upstream reference gaps. The official GKI table is not a direct readout of the Motorola's live, possibly customized kernel.

The on-device read-only tool now also checks whether the kernel's `/proc/kallsyms` lists export names `__ksymtab_rfkill_pause_polling` and `__ksymtab_usb_get_urb`, **without saving their addresses**. A missing kallsyms entry is inconclusive when kallsyms exports are hidden; neither a listed symbol name nor a CRC witness alone authorizes module loading.

## Read-only normal-boot audit

This PR supplies scripts/nevada-ar9271-live-core-kmi-witness.py plus ci/nevada-ar9271-core-kmi.tsv containing 101 candidate CRC requirements extracted from the actual corrected PR #15 module artifact.

The script identifies loaded stock modules using /proc/modules, reads their original ELF __versions records from /vendor_dlkm, /system_dlkm, /odm_dlkm and standard vendor/system directories, and counts matching or conflicting CRC demands. It skips ambiguous duplicate module filenames rather than assuming a loaded module's disk path. For files that cannot be read as the ordinary Termux user, it optionally uses KernelSU su only for a read-only cat operation.

It never calls insmod, modprobe, dd, flash, chmod, chcon, signing, CRC replacement, boot patching, or any hardware-changing operation.

### Run on the rooted Moto G Play 2026 using Termux

These commands use your existing GitHub CLI access:

~~~bash
pkg install python gh -y
mkdir -p "$HOME/nevada-live-kmi"

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-ar9271-live-core-kmi-witness.py?ref=nevada-ar9271-live-core-kmi-witness" \
  > "$HOME/nevada-live-kmi/witness.py"

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/ci/nevada-ar9271-core-kmi.tsv?ref=nevada-ar9271-live-core-kmi-witness" \
  > "$HOME/nevada-live-kmi/core-kmi.tsv"

python "$HOME/nevada-live-kmi/witness.py" \
  --manifest "$HOME/nevada-live-kmi/core-kmi.tsv" \
  --output "$HOME/nevada-live-kmi/live-core-kmi.json"
~~~

Share the console summary and optionally the saved JSON report. The JSON contains module names and CRC requirements, not the proprietary module binaries.

If root permission for a stock module is requested, allowing *read-only cat* for this audit is sufficient. If module paths are unreadable or ambiguous the report documents missing evidence; it will not invent a match.

## Important limitations

**A loaded stock module importing a given CRC only corroborates it; it does not expose the authoritative CRC exported from the running vmlinux kernel.** Even 101/101 import witnesses would not authorize installation without verifying all live kernel exports, actual symbol whitelist, CFI, module signing and firmware/USB support.

The compiled experimental Atheros modules still report vermagic **5.15.180-MMI-W1WN36.18-114-dirty** while the phone runs **5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692**. The original stock config enables CONFIG_MODULE_SIG_PROTECT=y. Do not spoof CRCs, patch vermagic, bypass module signatures, replace existing stock Wi-Fi or force-load experimental drivers.

If the 18 remaining symbols still lack corroboration after a normal-boot scan, prioritize obtaining a genuine matching-kernel export table before considering an AR9271 module install.

## CI scope

GitHub Actions checks Python syntax, a pinned 101-symbol candidate manifest, saved recovery witness summary and synthetic ELF fixture parsing. A green CI result **does not mean the normal-boot device is compatible**. The actual device audit is run by the user in Termux.
