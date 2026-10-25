# XT2615-1 nevada — mac80211 genksyms type tracing

## Proven facts

Android firmware `W1WNS36.18-114-1` runs `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`. The **live** `cfg80211` and `mac80211` ELF Build-ID note hashes match modules extracted from the uploaded, working TWRP recovery vendor boot image.

Atheros AR9271 `ath9k_htc` and its helpers compile successfully, and the LED-free Kconfig experiment removed both unavailable mac80211 LED symbol imports.

The one known remaining CRC mismatch:

| Export | Reference (actual live mac80211 build) | Candidate import |
|---|---|---|
| `ieee80211_alloc_hw_nm` | `0x561b7fc2` | `0x55ebf907` |

The stock-config-based full compilation test did *not* change this CRC.

## Objective

A **short, non-flashable source-type experiment** to determine whether stock vs generic-GKI config differences cause differences in `ieee80211_alloc_hw_nm`'s transitive C type definitions, especially `struct ieee80211_ops`.

The `scripts/nevada-ieee80211-symtypes-trace.sh` test:

1. Checks out the exact public Motorola kernel source revision `0fa176ca7f56c349b51acd83684284c02ced5854`.
2. Generates two separate Kconfig trees (public GKI and the user-provided stock config).
3. Enables the same temporary `CFG80211=m`/`MAC80211=m` and `MODVERSIONS=y` on both sides, uses ThinLTO to bound RAM, and turns off stock symbol trimming whose private absolute whitelist is unavailable.
4. Compiles only `net/mac80211/main.o` with `KBUILD_SYMTYPES=1` to obtain the kernel's own `genksyms` type trace.
5. Publishes source type traces and a diff, not module or boot-image binaries.

**Interpretation:** Differences point to conditional C types worth investigating. If the traces are identical, the persistent CRC discrepancy more strongly implicates source revision differences or ABI backports, not the compared config toggles. Even a matching CRC would not yet verify correct module loading.

This experiment does **not** reconstruct Motorola's original `mac80211` source-level genksyms types from its ELF binary. It does not change live kernel, TWRP, KernelSU, `init_boot`, `vendor_boot`, or internal Wi-Fi. It does not package or install modules, bypass CRC/signatures, or attempt a flash.

## How to use

The PR triggers a new GitHub Actions run. Review `README-NO-FLASH.txt` and `gki-vs-stock-symtypes.diff` in the artifact. If the workflow fails early, inspect the logs and fix the *diagnostic command*, without touching stock device partitions.

Reference for genksyms and module versioning:
https://docs.kernel.org/6.1/kbuild/modules.html
