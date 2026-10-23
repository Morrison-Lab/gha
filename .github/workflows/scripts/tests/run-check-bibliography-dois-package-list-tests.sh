#!/usr/bin/env bash
# The preinstalled-toolchain step of check-bibliography-dois installs the same
# R packages as the setup-r-dependencies step; nothing else keeps the two
# lists in step (gha#1208).
set -euo pipefail

root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
action="$root/check-bibliography-dois/action.yml"

from_setup=$(grep -oE 'any::[A-Za-z0-9.]+' "$action" | sed 's/^any:://' | sort)
from_pak=$(grep 'pak::pkg_install' "$action" | grep -oE '"[A-Za-z0-9.]+"' | tr -d '"' | sort)

if [ -z "$from_setup" ] || [ -z "$from_pak" ]; then
  echo "::error::could not read a package list from $action" >&2
  exit 1
fi
if [ "$from_setup" != "$from_pak" ]; then
  echo "::error::package lists differ: setup-r-dependencies has [$from_setup], pak has [$from_pak]" >&2
  exit 1
fi
echo "Both steps install: $(echo "$from_pak" | tr '\n' ' ')"
