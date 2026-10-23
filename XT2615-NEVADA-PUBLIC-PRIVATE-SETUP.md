# XT2615-1 Nevada TWRP: free public runner + private firmware/results

## Architecture

- **PUBLIC build repository:** `BalsacTheJew666/Action-TWRP-Builder`
- **PRIVATE firmware/output repository:** `BalsacTheJew666/Attempt-at-building-recovery-with-actions`
- **Device:** Motorola XT2615-1, `nevada`, Boost, Android 16
- **Firmware:** `W1WNS36.18-114-1`, kernel `5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692`, 2026-04-01 security patch
- **Public Actions workflow:** `.github/workflows/XT2615-Nevada-Public-Private-Output.yml`
- **Runner:** `ubuntu-22.04` on a **public** repository: 4 vCPUs, 16 GB RAM
- **Stock overlay:** private ZIP fetched via authenticated GitHub Contents API (never checked into public repository).
- **Build outputs:** private draft GitHub Release (NEVER a public workflow artifact).

## Required one-time GitHub setup (on your phone)

The ChatGPT GitHub connector can update repository files, but cannot create GitHub Actions secrets. **You must add the secret yourself. Never paste the token in chat.**

1. Open GitHub [Fine-grained Personal Access Tokens](https://github.com/settings/personal-access-tokens/new) while signed in as `BalsacTheJew666`.
2. Choose a descriptive token name such as `nevada-private-transfer`, and a short expiration (e.g. 7-30 days).
3. Set **Resource owner** to `BalsacTheJew666`.
4. Choose **Only select repositories** and select ONLY `Attempt-at-building-recovery-with-actions` (the PRIVATE repository).
5. Under Repository permissions, set **Contents: Read and write** (needed to read the ZIP and write private Release assets); leave other permissions at minimum/default. Metadata read is automatic.
6. Generate the token and COPY it once. Keep it confidential.
7. Go to [the PUBLIC repository Actions secrets](https://github.com/BalsacTheJew666/Action-TWRP-Builder/settings/secrets/actions) → **New repository secret**.
8. Set **Name** to `NEVADA_PRIVATE_REPO_TOKEN` and **Secret** to the token's exact value. Save. Do not upload the token as a file or commit it to Git.
9. To launch, open the [XT2615 Public Builder workflow](https://github.com/BalsacTheJew666/Action-TWRP-Builder/actions/workflows/XT2615-Nevada-Public-Private-Output.yml), select **Run workflow**, choose **main**, and start.

For release downloads afterward: go to the [PRIVATE repository Releases](https://github.com/BalsacTheJew666/Attempt-at-building-recovery-with-actions/releases). Draft releases appear to repository maintainers; find the draft with your workflow run ID.

## Exactly what is public and private?

**Public and visible to other GitHub users:** workflow YAML, source URLs, step names, runner resource telemetry, and the fact that the run happened. Public GitHub Actions logs may still expose incidental nonsecret metadata. Avoid inserting proprietary information into custom workflow messages.

**Private:** the original firmware ZIP in the private repository, temporary downloaded bytes in the ephemeral runner, compiler diagnostic logs (packaged only in a private draft release), and any compiled `vendor_boot.img` in that private draft release.

The build necessarily processes the private hardware files on GitHub's temporary public-repository runner. Secrets are masked by GitHub and explicitly passed only to the *download* and *private delivery* steps, not to `repo sync` or compilation. Even so, externally sourced build scripts operate in the same ephemeral environment and should be trusted or reviewed; no CI setup can promise absolute prevention of data leakage from untrusted build code.

The new public workflow is **manual-only** (`workflow_dispatch`), has no public artifact upload, does not check out untrusted pull requests, does not enable public Releases, and does not flash the phone.

## Progress and troubleshooting

The workflow has seven principal phases: token preflight, private ZIP checksum, cleanup/dependencies, minimal TWRP source sync, pinned Nevada device tree checkout, matching firmware overlay, serial `vendorbootimage` compilation, then private draft release delivery. It is configured to finish compilation and upload a PRIVATE ZIP of logs on normal failures.

If any stage fails, open **PRIVATE repository → Releases**, look for a draft named `XT2615-1 private build <GitHub run ID>`, and download `PRIVATE-build-logs.zip`. If the runner itself crashes or is forcibly terminated, the delivery step may not execute and a draft release may not exist.

**Important limitation:** The standard free GitHub public runner has 16 GB RAM but comparatively restricted disk space. The workflow frees unused software and refuses to continue if storage is insufficient. Successful compilation remains unproven, and the generated recovery would remain experimental.

## Do not flash yet

The TWRP base is 12.1 but the installed device runs Android 16, and metadata validation cannot establish compatibility with its AVB, FBE decryption, touchscreen or boot partition configuration. The output must be inspected and a tested stock-image restoration path established before any flashing.

## Security hygiene

- Restrict token to exactly one private repository, avoid `All repositories` and unnecessary scopes.
- Do not add the token to workflow inputs or `README.md`.
- Rotate/revoke the token after building if it is no longer needed.
- Only allow trusted collaborators to change the public repository's workflow files; GitHub Actions secrets are repository-scoped, not scoped to one individual workflow.
- Do not enable pull-request triggers for this secret-using workflow.
