# Motorola XT2615-1 nevada: AR9271 TESTMODE-corrected diagnostic rebuild

## Finding confirmed by PR #14 / GitHub Actions #40357269940

Your preserved, stock `mac80211.ko` exports `ieee80211_alloc_hw_nm` with Linux modversion CRC **`0x561b7fc2`**. The original experimental `ath9k_htc.ko` imports that symbol at **`0x55ebf907`**, making that prototype an incompatible dependency.

The stock module's direct ELF `.BTF` examination revealed `testmode_cmd` and `testmode_dump` in `struct ieee80211_ops`, but no optional `sta_add_debugfs`. That gave an evidence-based source configuration: **`CONFIG_NL80211_TESTMODE=y`**, **`CONFIG_MAC80211_DEBUGFS=n`**. A controlled FullLTO compile from the pinned Motorola source generated:

| Test | Exported ieee80211_alloc_hw_nm CRC |
| --- | --- |
| NL80211_TESTMODE=n, debugfs=n | `0x55ebf907` |
| NL80211_TESTMODE=y, debugfs=n | **`0x561b7fc2`**, matches stock |

The earlier all-four-module build had **30 Wi-Fi-framework import instances** checked against the actual stock `cfg80211.ko` / `mac80211.ko` exports, 29 matching and the sole mismatching `ieee80211_alloc_hw_nm` import. Other imports matched experiment-generated Atheros or kernel symbols, **not actual core kernel ABI**.

## Purpose of PR #15

Run a **diagnostic-only** four-module rebuild with the new proven source flag, preserve prior safeguards, and check whether **all 30 previously verified stock Wi-Fi import CRC entries** now match the saved snapshot.

The newly added shell script extends the known successful stock-config-based compile of `ath.ko`, `ath9k_hw.ko`, `ath9k_common.ko`, and `ath9k_htc.ko`, but changes:

- `CONFIG_NL80211_TESTMODE=y`; `CONFIG_MAC80211_DEBUGFS=n`—derived from stock BTF.
- Temporarily patch only the `ATH9K_HTC` Kconfig selection of missing optional `MAC80211_LEDS` exports, as in previous successful compilation.
- Keep `CONFIG_CFI_CLANG=y` and `CONFIG_MODVERSIONS=y`.
- Use **ThinLTO** instead of stock FullLTO for a resource-bounded GitHub Actions complete kernel diagnostic build; the previous identical-source single-object tests generated the same relevant symbol CRC under either LTO mode.
- Disable `TRIM_UNUSED_KSYMS` because Motorola's original private KMI symbol whitelist remains unavailable.
- Start from the user-provided stock `.config` with pinned SHA256 `e3cdaf997a7e2eb70e441944bdfd9af359aa82e8a2d5cb9534d2bce5fcd4a78a`, while temporarily enabling `CFG80211=m` and `MAC80211=m` to build dependency modules for the experiment.

The Python static post-build verifier parses real `__versions` ELF import records for all four Atheros modules, verifies the 30 previously SHA256-audited stock wireless reference entries, and **fails the job if any do not match**. It separately labels imports satisfied by **experimental** Atheros modules or **experimental** `vmlinux.symvers`. It never calls those imported CRCs validated against the actual phone's kernel.

### Critical safety boundary

Passing **30/30 stock Wi-Fi import CRCs is not the same as a loadable kernel module**. Before installing any `.ko`, one still needs a trustworthy live core KMI import comparison, target-compatible compiler/toolchain and module `vermagic`, CFI and LTO cross-module details, SELinux/module signing policy, OTG support, Atheros firmware `htc_9271-1.4.0.fw`, and actual hardware testing.

The only outputs are a **clearly NOT-INSTALLABLE diagnostic artifact** containing experimental ELF modules, resolved configs, KMI candidate symbol tables and JSON evidence, plus a compiler log. **Never `insmod` these ELF files, flash an experimental kernel, patch any CRC/vermagic, replace stock mac80211/cfg80211, or risk working KernelSU and custom recovery.** No direct phone change is requested or performed.
