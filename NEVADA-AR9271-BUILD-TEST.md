# Nevada NetHunter AR9271 / ath9k_htc compile test

This workflow is an **experimental compilation test, NOT a working NetHunter driver package**.

- Trigger manually: **Actions → XT2615-1 Nevada - AR9271 USB WiFi Compile Test → Run workflow** (after merging the PR).
- Builds on pinned public Motorola 5.15.180 source, using Ubuntu-host Clang and ThinLTO to fit GitHub Actions resources.
- Sets `CFG80211=m`, `MAC80211=m` temporarily to satisfy upstream driver Kconfig dependencies. **Those newly built modules are NOT the device's working stock modules.**
- Tests `ATH9K_HTC=m`; collects `ath9k_htc.ko`, `ath9k_common.ko`, `ath9k_hw.ko`, `ath.ko` plus config/report and module symbol information.
- Does not upload generated `cfg80211.ko`, `mac80211.ko`, any boot image, or KernelSU/TWRP image. No flashing and no changes to the device.
- The build artifacts must **NOT** be installed, packaged for Magisk, or manually insmod'd.
- After a successful build, compare all module imports against the *actual* firmware-matched exported symbols/CRC values from the running device's wireless frameworks. Then align Android Clang, Full LTO, KMI, module signature, localversion and dependency loading.

Hardware: AR9271-based adapter, `ath9k_htc`. It requires USB-OTG support and the separate open firmware file `htc_9271.fw`. Supporting a chipset in Kconfig does not prove the adapter is detected or supports monitor/injection on this build.

Primary references:
- https://wireless.docs.kernel.org/en/latest/en/users/drivers/ath9k_htc.html
- https://source.android.com/docs/core/architecture/kernel/abi-monitor
