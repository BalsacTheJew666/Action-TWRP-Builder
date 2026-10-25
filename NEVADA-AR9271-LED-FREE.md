# Nevada XT2615-1 — AR9271 LED-free ABI experiment

## Why this exists

Successful [AR9271 compile test #1](https://github.com/BalsacTheJew666/Action-TWRP-Builder/actions/runs/40165099405) produced four Atheros `.ko` binaries, but static comparison against the recovered (TWRP recovery) stock wireless modules showed the **ath9k_htc.ko** imports below:

| symbol | Compiled CRC | Recovered stock module result |
|---|---|---|
| `ieee80211_alloc_hw_nm` | `0x55ebf907` | `0x561b7fc2` (mismatch) |
| `__ieee80211_get_radio_led_name` | `0xc2669f03` | not exported |
| `__ieee80211_create_tpt_led_trigger` | `0x0b3c1b69` | not exported |

The Atheros driver Kconfig conditionally selects `MAC80211_LEDS` when the kernel has a LED class. Our old experimental config had `CONFIG_MAC80211_LEDS=y`.

## The controlled change

The script in `scripts/nevada-ar9271-ledfree-experiment.sh` patches exactly **one conditional Kconfig selection** inside the upstream `config ATH9K_HTC` stanza (in a temporary checkout on the CI runner), then requires `# CONFIG_MAC80211_LEDS is not set`. It **keeps `CONFIG_LEDS_CLASS` intact**, to avoid altering unrelated Android functionality.

The new GitHub Actions workflow runs on this PR and by manual dispatch after merging. It builds `ath9k_htc.ko` plus the original helper modules in a **temporary GKI/ThinLTO test environment**. It extracts `__versions` imports, fails the job if either known missing LED import remains, and records whether the `ieee80211_alloc_hw_nm` CRC has changed relative to stock reference `0x561b7fc2`. It does not force a fabricated CRC match.

## Important caveats

This test compiles its own non-stock `cfg80211` and `mac80211` dependencies. None of the modules it generates should be loaded into the phone. The firmware-matched stock wireless modules are only examined **offline outside public GitHub**; neither proprietary module nor boot image is uploaded to this repo.

The actual *normal-boot* wireless modules, Android Clang 14.0.7 vs runner Clang, FullLTO vs diagnostic ThinLTO, exact KMI, module signature/trust, CFI, and firmware `ath9k_htc/htc_9271-1.4.0.fw` still require verification.

**Do not flash, install, `insmod`, or repackage as a Magisk module.** The purpose is to determine whether removing optional LED references resolves the 2 unresolved imports, and whether it influences the remaining CRC mismatch.
