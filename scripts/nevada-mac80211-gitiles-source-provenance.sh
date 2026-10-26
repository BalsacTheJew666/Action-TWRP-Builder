#!/usr/bin/env bash
# Find the exact public Android common-kernel commit referenced by the
# user's loaded mac80211.ko. Does not load/install any module or touch phone.
set -Eeuo pipefail
: "${WORK_DIR:?Missing WORK_DIR}"
FOUND_OUTPUT="${FOUND_OUTPUT:-${GITHUB_OUTPUT:?Missing GITHUB_OUTPUT}}"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"
prefix=6558a72298ed
url='https://android.googlesource.com/kernel/common'
export GIT_TERMINAL_PROMPT=0
report="$WORK_DIR/source-provenance.txt"
{
  echo "Device: Motorola XT2615-1 nevada / Android 16"
  echo "Running kernel: 5.15.180-android13-8-00018-g9b2308ac0ad6-ab14563692"
  echo "Live mac80211 vermagic: 5.15.180-android13-8-g6558a72298ed"
  echo "Live mac80211 exported ieee80211_alloc_hw_nm CRC: 0x561b7fc2"
  echo "Requested candidate source SHA prefix: $prefix"
  echo "Official source repository: $url"
} > "$report"
echo "=== Validating Gitiles short-SHA lookup with known kernel commit ==="
known_full='9b2308ac0ad616788fb57ba688aa07f0ff221355'
known_short='9b2308ac0ad6'
for type in full short; do
  if [[ "$type" == full ]]; then target="$known_full"; else target="$known_short"; fi
  code="$(curl -sSL --retry 1 --connect-timeout 15 --max-time 40 \
    -w '%{http_code}' -o "$WORK_DIR/positive-control-$type.json" \
    "$url/+/$target?format=JSON" || true)"
  echo "Gitiles positive control ($type): HTTP $code" | tee -a "$report"
  if [[ "$code" == "200" ]]; then
    if python3 - "$WORK_DIR/positive-control-$type.json" "$known_full" <<'PY'
import json,sys
from pathlib import Path
s=Path(sys.argv[1]).read_text()
if s.startswith(")]}'"): s=s.split('\n',1)[1]
d=json.loads(s)
commit=d.get('commit')
if commit != sys.argv[2]:
    raise SystemExit('Positive control SHA did not match the known GKI release')
print('Positive control verified:',commit)
PY
    then
      echo "Gitiles positive control ($type): verified" | tee -a "$report"
    else
      echo "Gitiles positive control ($type): malformed or unexpected content" | tee -a "$report"
    fi
  fi
done
if ! grep -q 'Gitiles positive control (short): verified' "$report"; then
  echo "LOOKUP_METHOD_NOT_VALIDATED: known public GKI commit did not resolve via short SHA; target 404 would be inconclusive." | tee -a "$report"
fi

echo "=== Resolving exact commit $prefix via official Android Gitiles ==="

# Gitiles returns JSON preceded by a 4-character XSSI prefix. It can resolve
# abbreviated SHA IDs when reachable. Check before trying a Git fetch.
if curl -fLSs --retry 2 --connect-timeout 15 --max-time 55 \
  "$url/+/$prefix?format=JSON" -o "$WORK_DIR/gitiles-commit.txt"; then
  if python3 - "$WORK_DIR/gitiles-commit.txt" "$WORK_DIR/resolved-commit.txt" "$prefix" <<'PY'
import json,sys
from pathlib import Path
data=Path(sys.argv[1]).read_text()
if data.startswith(")]}'"):
    data=data.split('\n',1)[1]
d=json.loads(data)
sha=d.get('commit','')
if not isinstance(sha,str) or len(sha)!=40 or not sha.startswith(sys.argv[3]):
    raise SystemExit('Gitiles did not confirm requested SHA prefix')
Path(sys.argv[2]).write_text(sha+'\n')
print('Official Gitiles resolved commit:',sha)
PY
  then
    echo "Gitiles SHA resolution: verified" >> "$report"
  else
    echo "Gitiles responded but no valid matching 40-char commit was proven." >> "$report"
  fi
else
  echo "Gitiles abbreviated SHA lookup unavailable or not found." >> "$report"
fi

if [[ ! -s "$WORK_DIR/resolved-commit.txt" ]] && ! grep -q 'Gitiles positive control (short): verified' "$report"; then
  echo "LOOKUP_UNRELIABLE: No exact source could be verified and Gitiles short-SHA lookups did not pass the positive control." | tee -a "$report"
fi

if [[ ! -s "$WORK_DIR/resolved-commit.txt" ]]; then
  echo "SOURCE_NOT_VERIFIED: No exact published SHA resolved; no fallback." | tee -a "$report"
  echo "found=false" >> "$FOUND_OUTPUT"
  exit 0
fi

exact_sha="$(cat "$WORK_DIR/resolved-commit.txt")"
mkdir -p "$WORK_DIR/source"
cd "$WORK_DIR/source"
git init -q
git remote add origin "$url"
if ! timeout 240 git -c protocol.version=2 fetch --quiet \
  --no-tags --depth=1 origin "$exact_sha"; then
  echo "SOURCE_NOT_VERIFIED: Official server did not allow direct fetch." | tee -a "$report"
  echo "found=false" >> "$FOUND_OUTPUT"
  exit 0
fi
git checkout -q --detach FETCH_HEAD
actual="$(git rev-parse HEAD)"
if [[ "$actual" != "$exact_sha" ]]; then
  echo "SOURCE_NOT_VERIFIED: Git checkout SHA mismatch" | tee -a "$report"
  echo "found=false" >> "$FOUND_OUTPUT"
  exit 0
fi
kernelversion="$(make -s kernelversion)"
echo "Fetched exact source SHA: $actual" | tee -a "$report"
echo "Fetched source Linux version: $kernelversion" | tee -a "$report"
if [[ "$kernelversion" != 5.15.180 ]]; then
  echo "SOURCE_NOT_VERIFIED: Linux version differs from stock mac80211 module." | tee -a "$report"
  echo "found=false" >> "$FOUND_OUTPUT"
  exit 0
fi
echo "SOURCE_VERIFIED: Exact mac80211 SHA exists and source tree version matches." | tee -a "$report"
echo 'found=true' >> "$FOUND_OUTPUT"
echo "sha=$actual" >> "$FOUND_OUTPUT"
