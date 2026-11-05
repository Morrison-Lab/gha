#!/usr/bin/env bash
# Print `fingerprint=<hash>` of the Quarto freeze directory's file names,
# sizes and modification times, for a step output (gha#1529).
#
# Two fingerprints differ exactly when a render wrote, replaced or removed a
# frozen result, so a preview can skip saving an unchanged freeze cache.
# A missing or empty directory prints the hash of empty input.
#
# Environment: FREEZE_DIR, the freeze directory (default: `_freeze`).
set -euo pipefail
dir="${FREEZE_DIR:-_freeze}"
if [ -d "$dir" ]; then
  listing="$(cd "$dir" && find . -type f -printf '%p %s %T@\n' | LC_ALL=C sort)"
else
  listing=""
fi
echo "fingerprint=$(printf '%s' "$listing" | sha256sum | cut -d' ' -f1)"
