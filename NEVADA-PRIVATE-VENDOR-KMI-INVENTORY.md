# XT2615-1 Nevada: PRIVATE on-device vendor module import inventory

**Research-only. No module load, kernel patch, flash, root changes or boot image.**

## Why

- Official Google GKI **14563692** has **8,471** actual public `vmlinux` exports, and the two needed AR9271 exports `usb_get_urb` / `rfkill_pause_polling` are absent. Source whitelist retention was proved in PR #23.
- Your successful normal-boot XT2615-1 read-only audit examined **181 loaded stock module ELF files**, matched **82/101** Atheros core CRC requirements with **zero conflicts**. The remaining 19 are unwitnessed, not automatically incompatible.
- PR #24 (public GKI export superset) can represent 8,471 public baseline export names plus two Atheros names, but the **original Motorola build-time vendor ABI symbol list is not yet available**.

The safe next question is: **what names and imported CRC requirements do the other 181 loaded stock modules demand that the public GKI baseline does not provide?**

### What the new scanner does

The public code in `scripts/nevada-vendor-core-abi-private-inventory.py` is run by you inside Termux, not by public GitHub Actions:

1. Reuses your already tested read-only `witness.py` for current `/proc/modules` names, root-assisted `find`/read of existing on-disk `.ko` files, bind-mount alias deduplication and strict same-name binary identity. Does not access boot partitions.
2. Parses all imported module symbols from existing ELF `__versions` records, not just the AR9271 101-symbol manifest. It does not copy a proprietary module or raw firmware.
3. Compares the import requirements with the actual official public GKI `vmlinux.symvers` downloaded **locally** (SHA256 `bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0`, 8,471 unique exports). Reports:
   - Exact public GKI CRC matches
   - Same-name CRC differences (could be vendor-specific or module-provided; don't force resolution)
   - Symbols absent from *public* GKI (may be provided by other vendor modules, and **cannot automatically be added to the kernel whitelist**)
   - Conflicting CRC requirements across stock modules
   - Counts for 101 Atheros core witness symbols and two still-missing official exports
4. Saves a **private local JSON** with individual symbol names and CRCs under your Termux home; only an aggregate console summary need be shared. Nothing is uploaded to GitHub or a server by the Python code.

The GitHub Actions workflow uses an **entirely synthetic module ELF**, and a public GKI file. It verifies success and conflict classification end-to-end without any real device files or metadata.

### User-controlled, read-only Termux run

```bash
cd "$HOME/nevada-live-kmi" || exit 1

gh api -H "Accept: application/vnd.github.raw+json" \
  "repos/BalsacTheJew666/Action-TWRP-Builder/contents/scripts/nevada-vendor-core-abi-private-inventory.py?ref=nevada-ar9271-private-vendor-abi-inventory" \
  > vendor-inventory.py.new && \
python -m py_compile vendor-inventory.py.new && \
mv vendor-inventory.py.new vendor-inventory.py || exit 1

curl -fLSs --retry 2 \
  "https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers" \
  -o official-14563692-vmlinux.symvers || exit 1

echo "bdcf93a69e5513ffefd916f9b9cceaf4c1f14657e3aeaf52bb0cd0cd5ea655c0  official-14563692-vmlinux.symvers" | sha256sum -c - || exit 1

python vendor-inventory.py \
  --witness-script witness.py \
  --official-gki-symvers official-14563692-vmlinux.symvers \
  --core-import-manifest core-kmi.tsv \
  --report vendor-private-kmi-inventory.json \
  | tee vendor-kmi-summary.txt
```

**Only send the console summary** (`vendor-kmi-summary.txt`) initially. Do not share raw firmware, boot images, recovery images or proprietary `.ko` files. The JSON report stores module name and symbol CRC metadata locally, with restrictive file permissions by default.

### Interpretation and limits

Any listed "not an official public GKI export" imported symbol might be exported by **another module** rather than `vmlinux`. This tool cannot reconstruct the complete original `abi_symbollist.raw` or prove core export compatibility by itself. It also doesn't cover unloaded drivers, all built-in interfaces, signature protection, exact `vermagic`, CFI/LTO, USB hardware or Wi-Fi firmware.

No symbols are force-exported by this step, and **do not flash or `insmod` the experimental AR9271 modules**.

### Public source anchors

- https://ci.android.com/builds/submitted/14563692/kernel_aarch64/latest/raw/vmlinux.symvers
- https://source.android.com/docs/core/architecture/kernel/howto-symbol-lists
- https://github.com/BalsacTheJew666/Action-TWRP-Builder/pull/23
