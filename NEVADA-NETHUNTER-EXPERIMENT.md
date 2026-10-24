# Motorola XT2615-1 (nevada) — NetHunter kernel preparation

**Status: source/configuration build experiment only. No flashable image and no verified NetHunter runtime.**

This lives on a separate branch from the working XT2615-1 TWRP builder.
It does not modify the TWRP vendor_boot recipe, use the private firmware
overlay, install root, or flash the phone.

## Source compatibility gate

- Motorola Android 16 source: `MotorolaMobilityLLC/kernel-mtk`
- Branch: `android-16-release-w1wn36.18-114`
- Pinned SHA: `0fa176ca7f56c349b51acd83684284c02ced5854`
- Source Makefile reports **5.15.180**.
- The later reported XT2615-1 firmware `W1WNS36.18-114-6` and running
  kernel **5.15.189** are **NOT** matched to this source. The earlier
  TWRP experiment targeted firmware `W1WNS36.18-114-1`.
- Consequently, compiled output MUST NOT be inserted into either firmware's
  boot image or flashed until the **currently installed** boot/vendor_boot,
  device tree, vendor module ABI, and exact matching source have been audited.

## What's actually implemented

The manual GitHub Actions job checks out a *pinned public kernel source*,
creates an arm64 GKI defconfig, and requests USB HID gadget, USB gadget
networking, Bluetooth RFCOMM, and in-tree cfg80211/mac80211 USB Wi-Fi support
for AR9271 (ath9k_htc), rt2800usb, rtl8187, and mt7601u.

The script verifies the generated .config and **fails** if dependencies
reject a requested setting. Successful compilation, if achieved, will only
produce `Image.gz`, the resulting config, checksum and build notes.

In Motorola's source defconfig, `USB_CONFIGFS_F_HID=y`,
`USB_CONFIGFS_MASS_STORAGE=y` and `BT_RFCOMM=y` are already set;
legacy HID source-code patches are not needed. Other Wi-Fi driver support
is experimental. These CONFIG options do **not** prove working injection,
adapter firmware availability, adequate USB OTG power, or Android userspace
NetHunter support.

## Genuine NetHunter source patches

No unverified Kali 3.x/4.x/5.x patch is blindly downloaded/applied.
If a **reviewed and compatible** patch is required, commit an explicit
`*.patch` file under `nevada-nethunter-patches/`. Before configuration,
the script applies each patch with `git apply --check` and stops on
the first conflict. Do not substitute patches from an unrelated device or
force an incompatible patch.

Kali reference: https://www.kali.org/docs/nethunter/nethunter-kernel-1-patching/
Kali Wi-Fi config: https://www.kali.org/docs/nethunter/nethunter-kernel-4-config-3/

## How to run (after reviewing/merging this PR)

1. Open the public repository's **Actions** tab.
2. Select **XT2615-1 Nevada NetHunter Kernel (experimental)**.
3. Use **Run workflow**, select the containing branch, leave external Wi-Fi on.
4. Inspect **nevada-nethunter-build-logs**, especially failed Kconfig checks.
5. If successful, **nevada-nethunter-NOT-FLASHABLE** holds the raw
   compiled Image.gz and config. It is **not** a boot.img, vendor_boot.img,
   or any installable kernel ZIP.

Only public Motorola source is used; the experimental image and logs are
uploaded as public-repository Actions artifacts. No private firmware files
or tokens are used by this workflow. Do not place proprietary overlays,
private logs, secrets, personal paths, or firmware backups in this branch.

## Required before making any flashable image

- Verify active slot, firmware build, and full `uname -r` at build time.
- Obtain/check the exact matching Motorola source and compiler.
- Compare `modinfo -F vermagic`/KMI for all stock vendor modules.
- Preserve the correct `boot.img`, `vendor_boot.img`, `init_boot.img`
  (if present), `dtbo.img`, and vbmeta for the active firmware.
- Rebuild with matching KMI/signed modules, preserve ramdisks/DTB/AVB format,
  and test with a recovery route. NetHunter app, root and firmware are separate.
- Do **not** use `fastboot flash recovery`; this platform uses vendor_boot
  for recovery. The build experiment never invokes fastboot.
