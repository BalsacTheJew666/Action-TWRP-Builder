# Nevada / XT2615-1: compile research-only kernel with 8,473 public GKI export names

**No flash, insmod, boot image packaging, module installation, root change, or recovery operation.**

## Building on the validated public export superset

The prerequisite GitHub workflow #40480619663 completed successfully:

- Exact official Google GKI 14563692 \`vmlinux.symvers\`: **8,471** unique exported \`vmlinux\` symbol names.
- Research-only public symbol whitelist adds exactly \`rfkill_pause_polling\` and \`usb_get_urb\`, yielding **8,473** names, SHA256 \`dd91c62dd62d322f0e862a7c4f0e719a2f2d2fb62d1423c2d705fed5668861cb\`.
- **99/101** distinct AR9271 core imports match official GKI CRCs. Exactly the two missing symbols lack official-GKI export CRCs.
- Pinned Motorola \`scripts/gen_autoksyms.sh\` recognized all 8,473 retention macros.

This is **not** an authentic original Motorola KMI whitelist: the original \`CONFIG_UNUSED_KSYMS_WHITELIST\` references a private vendor-built \`abi_symbollist.raw\`. Public GKI exports + two names might lack additional vendor exports. The compiled experiment cannot be treated as phone-safe.

## Current experimental compilation

Use the proven stock-based source build script from PR #15, but change the *research-only* flags:

- Preserve \`CONFIG_TRIM_UNUSED_KSYMS=y\` and point it to the generated public 8,473-name list, instead of disabling trimming.
- Preserve \`CONFIG_NL80211_TESTMODE=y\`, \`CONFIG_MAC80211_DEBUGFS=n\`, and disabling optional mac80211 LED-trigger imports in the isolated source checkout.
- Compile four experimental Atheros \`.ko\` modules and an isolated kernel using **Ubuntu Clang + ThinLTO** because prior test runners could not reproduce the precise Android Clang r450784e FullLTO stock toolchain. This is **NOT** stock-compatible module output.
- Confirm \`rfkill_pause_polling\` and \`usb_get_urb\` really appear in the *candidate compiled* \`vmlinux.symvers\`; verify their CRC values agree with the compiled \`ath9k_htc.ko\` \`__versions\` imports.
- Recheck the **30/30** already-verified stock Wi-Fi CRC reference comparisons. Report failure explicitly if the modified trimming build regresses these.
- Export only **text/JSON evidence and logs** from CI, never compiled \`.ko\`, \`Image.gz\`, \`boot.img\`, \`init_boot.img\`, flashable ZIPs, or proprietary firmware.

The compile output is throwaway CI research. It is safe to run in GitHub Actions because it cannot modify the real phone.

## Important remaining gates

A successful trimmed-code experiment is only *internal build self-consistency*. It does not mean:
1. Genuine Motorola vendor-specific KMI exports have all been preserved, because the original private \`abi_symbollist.raw\` is unavailable.
2. The public-source research kernel matches exact stock kernelrelease \`5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692\` or the stock Android Clang 14 FullLTO build.
3. Stock Wi-Fi modules would accept the kernel CFI, signer and module loader policies, or that KernelSU Next integration is preserved.
4. AR9271 hardware, USB OTG, \`htc_9271-1.4.0.fw\`, and NetHunter Wi-Fi operation have been verified. Physical adapter testing is still outstanding.

**Do not flash or insmod this experimental output.** Any eventual device build needs a full original KMI/vendor requirements audit, correct toolchain and rollback-safe KernelSU/recovery plan.
