# XT2615-1 Nevada: private 264-name live export owner triage

The user's read-only normal-boot vendor ABI audits established:

- 358 loaded module names, 181 found and readable stock ELF modules.
- 2472 distinct imported names; 1466 have matching exact official GKI 14563692 core CRCs.
- 1006 imports are not official GKI vmlinux exports. The stock module provider scanner attributed 742 of these to export declarations in readable module ELFs, with 742 matching provider CRCs and 0 conflicts.
- 264 names have no observed matching provider in the readable loaded module ELFs.
- 177 loaded modules lack a readable file path. This is incomplete coverage, not a core KMI mismatch.

The two AR9271 kernel blockers are usb_get_urb and rfkill_pause_polling. Earlier independent CI compiled them into a new experimental kernel and showed their candidate CRCs matched the experimental Atheros driver. This does NOT make any kernel or Atheros module installable.

## Research-only next step

This code reads only a private Termux JSON provider report, /proc/modules and /proc/kallsyms (read-only; KernelSU-assisted cat where needed). It classifies only the 264 unresolved names by any visible export-name owner label:

- live_loaded_module_owner_tag: a name tagged as exported by a currently loaded module
- visible_untagged_export_owner_unknown: export name visible without a module tag; NOT proof of vmlinux ownership
- multiple_or_unrecognized_owner_tags: conflicting/unknown owner attribution
- no_visible_ksymtab_name: not visible as export name; cannot prove absence

The scan discards kernel addresses, doesn't save or print them, and writes a private 0600 JSON. GitHub Actions tests with synthetic fake kallsyms/module files only. No device files are uploaded.

## Termux command

Run after this PR merges to main:

~~~bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-264-unresolved-live-export-triage.py?ref=main" \
  > unresolved-triage.py.new || exit 1

python -m py_compile unresolved-triage.py.new || exit 1
mv unresolved-triage.py.new unresolved-triage.py || exit 1

set -o pipefail
python unresolved-triage.py \
  --provider-report private-module-providers.json \
  --report private-264-unresolved-export-triage.json \
  | tee private-264-triage-summary.txt
~~~

Share only the aggregate console summary. Keep full JSON private. No proprietary module binary is needed.

## Hard safety boundary

Name-level kallsyms does not prove modversion CRCs, kernel ownership, ABI allowlist completeness, signer, CFI or root compatibility. The candidate public-GKI whitelist may lack Motorola vendor-only exports. The latest private 16GiB runner compiled an experimental Image.gz and matched 250/250 supplemental candidate CRCs, but it has not been boot validated. Never flash, force load, patch symbol values or alter internal Wi-Fi based on this report.
