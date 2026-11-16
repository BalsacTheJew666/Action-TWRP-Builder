# XT2615-1 Nevada: stock vendor module import inventory — READ ONLY

## Why this is now the required next gate

- Exact official Google GKI 14563692 release has **8,471** public core exports.
- The pinned public Motorola source's gen_autoksyms can retain those names plus \`rfkill_pause_polling\` and \`usb_get_urb\`, giving **8,473** names in a **public research-only** whitelist.
- The stock Motorola kernel was built with \`CONFIG_TRIM_UNUSED_KSYMS=y\` and references a private \`abi_symbollist.raw\`. The 8,473 names are **not verified as the genuine original Motorola KMI**.
- The rooted handset's prior on-device audit loaded **181 already-loaded stock module ELF files**, collapsed 181 Android mount aliases, and corroborated 82/101 AR9271 unique experimental core import CRC requirements with zero conflicts.

PR #27 already inventories **already-loaded** stock modules. This supplementary audit also checks **unloaded on-disk** module files from the normal stock module partitions, potentially identifying additional vendor dependencies missing from the public GKI export set. This is not a replacement for PR #27's loaded-module evidence. The next missing evidence is **which imports Motorola stock/vendor modules actually require** that are not exported from Google's public GKI build. A list of all original module *imports* narrows down the missing dependencies, but does not prove which providers are exports from \`vmlinux\` vs other stock \`.ko\`.

## What this tool actually does

The new \`scripts/nevada-stock-vendor-kmi-import-inventory.py\` runs ONLY when invoked by the user from Termux:

1. Reads a local copy of official Google GKI build 14563692 \`vmlinux.symvers\` (checks for exactly 8,471 unique public core exports).
2. Enumerates \`.ko\` files in standard mounted \`/vendor_dlkm\`, \`/system_dlkm\`, \`/odm_dlkm\`, \`/vendor\`, \`/system\` and \`/lib/modules\` paths, optionally using \`su -c find\` **only for reading directory paths**.
3. Resolves bind-mount aliases or duplicated module filenames using the SHA256-identity check already proven in the preceding on-device audit. Does not arbitrarily choose divergent vendor modules.
4. Reads ELF64 \`__versions\` imports from each selected module using normal filesystem permissions, or root \`su -c cat\` if needed.
5. Groups all module import CRCs by exported symbol name, compares them to official GKI \`vmlinux.symvers\`, and emits only **symbol names, CRCs, importing module names and diagnostic counters** into a local JSON report.

Output categories:

- \`public_gki_crc_match\`: an already-installed stock module needs a CRC also exposed by the official public GKI base.
- \`public_gki_crc_conflict\`: stock module imported CRC differs from the official GKI symbol's CRC. This is an ABI investigation point; no conclusion about the live kernel's actual exports is warranted.
- \`not_in_public_gki\`: a stock module imports a symbol absent from the public GKI \`vmlinux\` table. **It might come from another stock \`.ko\`**, or from a Motorola-modified core kernel. Do NOT automatically place all such names in a GKI-only whitelist: provider classification is still required.

The local script verifies the pinned official GKI symvers SHA256 `bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0` and writes its local JSON report with owner-only (`0600`) permissions. It does NOT export or upload the original vendor ELF module bytes, boot images, keys or firmware. The report is local and intentionally does NOT certify module loading, signature, CFI, \`vermagic\` or safe flashing.

## Run safely using your existing connected Termux + GitHub CLI

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-stock-vendor-kmi-import-inventory.py?ref=main" \
  > nevada-stock-vendor-kmi-import-inventory.py.new || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-ar9271-live-core-kmi-witness.py?ref=main" \
  > nevada-ar9271-live-core-kmi-witness.py.new || exit 1

python -m py_compile nevada-stock-vendor-kmi-import-inventory.py.new \
  nevada-ar9271-live-core-kmi-witness.py.new || exit 1

mv nevada-stock-vendor-kmi-import-inventory.py.new nevada-stock-vendor-kmi-import-inventory.py
mv nevada-ar9271-live-core-kmi-witness.py.new nevada-ar9271-live-core-kmi-witness.py

curl -fLSs --retry 2 \
  "https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers" \
  -o official-gki-14563692-vmlinux.symvers || exit 1

python nevada-stock-vendor-kmi-import-inventory.py \
  --official-symvers official-gki-14563692-vmlinux.symvers \
  --output nevada-stock-vendor-kmi-report.json \
  | tee nevada-stock-vendor-kmi-summary.txt
~~~

**Only the console summary is needed for next review.** The \`nevada-stock-vendor-kmi-report.json\` stays on the user's phone; do not upload it to any public repository. We can later inspect selected sanitized symbol names together.

## Safety and known limits

- This is **READ ONLY**, but root may request access for \`find\` or \`cat\`; review the script before allowing it.
- It cannot tell which \`__ksymtab\` core exports Motorola's kernel actually retained.
- Public-GKI CRC match alone does not prove the phone's live kernel's CRC.
- A stock module's non-public-GKI import could be satisfied by another stock module, so \`not_in_public_gki\` is not automatically a retained core export.
- The original private Motorola ABI whitelist has not been recovered; full KMI, signing, KernelSU Next, CFI, module vermagic and intact internal Wi-Fi remain prerequisites for a flashable device kernel.
- No AR9271 adapter hardware/firmware validation has happened yet. **Never flash experimental kernels or insmod the Atheros experimental modules.**

## CI scope

New GitHub Actions workflow only downloads Google's **public** release symbol table and executes an isolated synthetic ELF regression fixture. It cannot see the user's stock vendor binaries and must never request or publish them.
