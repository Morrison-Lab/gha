#!/usr/bin/env bash
# Install a pinned lychee release from the release cache (gha#1678).
#
# Reads the version from LYCHEE_VERSION (default 0.24.2, the version
# lychee-action v2.9.0 installs) and looks it up, with the CPU architecture,
# in the pins file (INSTALL_LYCHEE_PINS, default install-lychee-pins.txt beside
# this script).
# Downloads the archive through cached_download, which serves it from
# GHA_RELEASE_CACHE_DIR when the digest matches, and puts the binary in
# INSTALL_LYCHEE_DIR (default $RUNNER_TEMP/lychee/bin).
#
# Exit 0: lychee is installed there.
# Exit 3: this runner or version cannot use the cache path (not Linux, or no pin).
#         The caller falls back to lycheeverse/lychee-action.
# Any other non-zero exit: the download or extraction failed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pins="${INSTALL_LYCHEE_PINS:-$here/install-lychee-pins.txt}"
version="${LYCHEE_VERSION:-0.24.2}"
version="${version#v}"
os="${INSTALL_LYCHEE_OS:-$(uname -s)}"
arch="${INSTALL_LYCHEE_ARCH:-$(uname -m)}"
dest="${INSTALL_LYCHEE_DIR:-${RUNNER_TEMP:?RUNNER_TEMP is required}/lychee/bin}"

if [ "$os" != "Linux" ]; then
  echo "::notice::No cached lychee install for $os; using lychee-action."
  exit 3
fi

want="$(awk -v v="$version" -v a="$arch" \
  '$1 !~ /^#/ && $1 == v && $2 == a { print $3 }' "$pins")"
if [ -z "$want" ]; then
  echo "::notice::lychee $version on $arch has no pinned digest; using lychee-action."
  exit 3
fi

# shellcheck source=download-cache/cached-download.sh
source "${GHA_CACHED_DOWNLOAD:-$here/../../../download-cache/cached-download.sh}"

asset="lychee-${arch}-unknown-linux-gnu.tar.gz"
url="https://github.com/lycheeverse/lychee/releases/download/lychee-v${version}/${asset}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cached_download "$url" "$work/$asset" "$want"
if [ "$(_cd_sha256 "$work/$asset")" != "$want" ]; then
  echo "::error::$asset does not match its pinned SHA-256."
  exit 4
fi
tar -xzf "$work/$asset" -C "$work"
bin="$(find "$work" -type f -name lychee | head -n 1)"
if [ -z "$bin" ]; then
  echo "::error::No lychee binary in $asset; did the archive layout change?"
  exit 5
fi
mkdir -p "$dest"
install -m 755 "$bin" "$dest/lychee"
"$dest/lychee" --version
