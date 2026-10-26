# XT2615-1 Nevada: mac80211 CRC provenance / LTO matrix

## Why

Our verified stock `mac80211.ko` exports `ieee80211_alloc_hw_nm` with CRC `0x561b7fc2` (the running module's Build-ID matches our recovered recovery copy). AR9271 LED-free full ThinLTO compile requires `0x55ebf907`. A separate, non-LTO, single-object experiment from both public Motorola and May 2025 GKI produced `0x856d772a` for the same export, with identical `genksyms` type traces.

Before hunting additional source revisions or proposing driver changes, we need to establish which *build flag* accounts for `0x856d772a` vs `0x55ebf907`.

## Test

The new script compiles **only** `net/mac80211/main.o` from the pinned Motorola source commit `0fa176ca7f56c349b51acd83684284c02ced5854` using the user-uploaded stock `.config` under three otherwise-identical cases:

- `CONFIG_LTO_NONE=y`: extracts `__crc_ieee80211_alloc_hw_nm` from ELF absolute symbols.
- `CONFIG_LTO_CLANG_THIN=y`: reads the kernel's own generated `main.o.symversions` linker definitions; the `.o` itself is LLVM bitcode.
- `CONFIG_LTO_CLANG_FULL=y`: reads the same genksyms source with FullLTO enabled.

Both `CONFIG_CFG80211` and `CONFIG_MAC80211` are set to module in the diagnostic workspace, because the original stock base kernel intentionally loads them separately. `TRIM_UNUSED_KSYMS` is disabled because the original private Motorola symbol whitelist is unavailable. Stock original config SHA256 is verified on every CI run.

This is a **diagnostic-only** experiment, not stock-compatible output. The compiler used is runner Ubuntu Clang, not the Android Clang 14.0.7 r450784e toolchain used to build the firmware.

## Interpret results

- If no-LTO is `0x856d772a` while Thin/Full give `0x55ebf907`, we have isolated the difference to flags visible to `genksyms` and can focus on stock `mac80211` module provenance.
- If FullLTO gives `0x561b7fc2`, that would be an encouraging CRC candidate but **not** sufficient to consider installing AR9271: the exact source, all imported symbols, module `vermagic`, CFI, signatures, USB and firmware all must be independently verified.
- If all differ from the firmware, do **not** patch or spoof CRC/version fields. Continue source identification.

Outputs include plaintext CRC results, generated source-type traces and resolved Kconfigs, **not** `.ko` binaries. This PR does not flash, install or interact with the Motorola device and leaves KernelSU, TWRP, OrangeFox and its built-in wireless subsystem untouched.
