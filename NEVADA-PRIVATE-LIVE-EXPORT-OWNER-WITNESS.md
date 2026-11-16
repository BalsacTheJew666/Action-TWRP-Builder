# XT2615-1 Nevada — Read-only PRIVATE live ksymtab owner tags

## Confirmed prior device evidence

The original Moto G Play 2026 stock module inventory found **1,119** imported symbol names absent from official public GKI 14563692. A later device-only export-name attribution scan found:

- **822** names in possible on-disk stock module ELF \`__ksymtab_strings\` provider sections.
- **297** additional names visible as \`__ksymtab_*\` in the *live* \`/proc/kallsyms\` but not matched to those module export sections.
- **Zero** remaining names without either kind of *name evidence*.
- **Neither** \`usb_get_urb\` nor \`rfkill_pause_polling\` visible in those module export strings or live kallsyms export names.

**DO NOT interpret 297 entries as proven vmlinux/core exports.** Kallsyms may show modules as well as the built-in kernel. An untagged ksymtab symbol is not enough to assert owner or CRC.

## What the next read-only check adds

\`scripts/nevada-vendor-live-ksymtab-owner-witness.py\` takes the user's **private local** name-level report \`nevada-private-export-provider-report.json\`, rereads current \`/proc/kallsyms\` and \`/proc/modules\`, and classifies each of the 297 names according to whether its \`__ksymtab_* \` line ends with an explicit \`[module]\` tag.

Classes:
- **explicit_loaded_module_owner** — actual \`[module]\` tag and that module currently appears in \`/proc/modules\`.
- **untagged_export_owner_not_proven** — live ksymtab name exists but has no explicit module owner tag (NOT proof of vmlinux).
- **ambiguous_or_unrecognized_owner** — mixed owner tags or tag not in currently loaded modules.
- **no_longer_seen_in_kallsyms** — previously seen entry no longer appears.

This **does not read kernel addresses into the report**, determine authoritative export CRCs, or reconstruct the original private \`abi_symbollist.raw\`. It does not modify modules, kernel, root or partitions. The only write is a mode-0600 private JSON report under Termux.

### Run in Termux (user-controlled)

Use the existing \`nevada-live-kmi\` working folder with its earlier report:

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-vendor-live-ksymtab-owner-witness.py?ref=nevada-vendor-kmi-live-export-owner-witness" \
  > live-owner-witness.py.new || exit 1

python -m py_compile live-owner-witness.py.new || exit 1
mv live-owner-witness.py.new live-owner-witness.py || exit 1

set -o pipefail
python live-owner-witness.py \
  --provider-report nevada-private-export-provider-report.json \
  --output nevada-private-live-export-owners.json \
  | tee nevada-live-owner-summary.txt
~~~

Share **only the console summary** from \`nevada-live-owner-summary.txt\`. Leave the report JSON in Termux. Its names and loaded module tags are not uploaded by the script.

### Interpretation

A positive explicit module-owner match can help distinguish module-to-module imports from candidate built-in exports, but **none** of these name-level results by itself gives a correct CRC or a complete KMI whitelist. The already successful research build [#40481454888](https://github.com/BalsacTheJew666/Action-TWRP-Builder/actions/runs/40481454888) compiled both missing exports with internally matching CRCs and passed 30/30 stock Wi-Fi reference checks; that result is still **NOT INSTALLABLE** because the exact full vendor ABI, stock FullLTO/Android Clang, root integration and module loading have not been proved.

Do not flash/insmod experimental AR9271, spoof vermagic, force symbols or change SELinux. Working KernelSU Next, internal Wi-Fi and recoveries must stay intact.
