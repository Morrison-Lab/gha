#!/usr/bin/env bash
# Install a pinned Quarto release from the release cache (gha#1678).
#
# Reads VERSION from QUARTO_VERSION and looks it up, with the platform, in the
# pins file (INSTALL_QUARTO_PINS, default install-quarto-pins.txt beside this
# script).
# Downloads the .deb through cached_download, which serves it from
# GHA_RELEASE_CACHE_DIR when the digest matches, then installs it with dpkg.
#
# Exit 0: Quarto is installed.
# Exit 3: this runner or version cannot use the cache path (not Linux amd64,
#         no pin for the version, or no passwordless sudo).
#         The caller falls back to quarto-dev/quarto-actions/setup.
# Any other non-zero exit: the download or install failed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pins="${INSTALL_QUARTO_PINS:-$here/install-quarto-pins.txt}"
version="${QUARTO_VERSION:?QUARTO_VERSION is required}"
platform="${INSTALL_QUARTO_PLATFORM:-$(uname -s)-$(uname -m)}"

case "$platform" in
  Linux-x86_64 | linux-amd64) platform="linux-amd64" ;;
  *)
    echo "::notice::No cached Quarto install for $platform; using the setup action."
    exit 3
    ;;
esac

want="$(awk -v v="$version" -v p="$platform" \
  '$1 !~ /^#/ && $1 == v && $2 == p { print $3 }' "$pins")"
if [ -z "$want" ]; then
  echo "::notice::Quarto $version has no pinned digest; using the setup action."
  exit 3
fi

if ! sudo -n true 2> /dev/null; then
  echo "::notice::No passwordless sudo to install Quarto; using the setup action."
  exit 3
fi

# shellcheck source=download-cache/cached-download.sh
source "${GHA_CACHED_DOWNLOAD:-$here/../../../download-cache/cached-download.sh}"

asset="quarto-${version}-${platform}.deb"
url="https://github.com/quarto-dev/quarto-cli/releases/download/v${version}/${asset}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cached_download "$url" "$work/$asset" "$want"
if [ "$(_cd_sha256 "$work/$asset")" != "$want" ]; then
  echo "::error::$asset does not match its pinned SHA-256."
  exit 4
fi
sudo -n dpkg -i "$work/$asset"
quarto --version
