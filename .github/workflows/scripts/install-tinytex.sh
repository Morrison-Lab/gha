#!/usr/bin/env bash
# Install a pinned TinyTeX bundle from the release cache (gha#1705).
#
# Looks up VERSION (TINYTEX_VERSION, default the first pin) and the platform in
# the pins file (INSTALL_TINYTEX_PINS, default install-tinytex-pins.txt beside
# this script).
# Downloads the bundle through cached_download, which serves it from
# GHA_RELEASE_CACHE_DIR when the digest matches, and unpacks it into
# TINYTEX_HOME (default ~/.TinyTeX).
# Needs no sudo.
# An existing TinyTeX in TINYTEX_HOME is kept, as `quarto install tinytex`
# would not replace a working one on a runner that already has it.
# Its bin directory goes on PATH for later steps through GITHUB_PATH.
#
# Exit 0: TinyTeX is installed.
# Exit 3: this runner or version cannot use the cache path (not Linux x86_64,
#         or no pin for the version). The caller falls back to
#         `quarto install tinytex`.
# Any other non-zero exit: the download or unpacking failed.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
pins="${INSTALL_TINYTEX_PINS:-$here/install-tinytex-pins.txt}"
platform="${INSTALL_TINYTEX_PLATFORM:-$(uname -s)-$(uname -m)}"
home_dir="${TINYTEX_HOME:-$HOME/.TinyTeX}"

case "$platform" in
  Linux-x86_64 | linux-x86_64) platform="linux-x86_64" ;;
  *)
    echo "::notice::No cached TinyTeX install for $platform; using quarto install tinytex."
    exit 3
    ;;
esac

version="${TINYTEX_VERSION:-$(awk '$1 !~ /^#/ && NF { print $1; exit }' "$pins")}"
want="$(awk -v v="$version" -v p="$platform" \
  '$1 !~ /^#/ && $1 == v && $2 == p { print $3 }' "$pins")"
if [ -z "$want" ]; then
  echo "::notice::TinyTeX $version has no pinned digest; using quarto install tinytex."
  exit 3
fi

add_to_path() {
  local bin
  bin="$(find "$home_dir/bin" -mindepth 1 -maxdepth 1 -type d 2> /dev/null | head -n 1)"
  if [ -z "$bin" ]; then
    echo "::error::No TinyTeX bin directory under $home_dir."
    exit 4
  fi
  if [ -n "${GITHUB_PATH:-}" ]; then
    echo "$bin" >> "$GITHUB_PATH"
  fi
  echo "TinyTeX bin directory: $bin"
}

if [ -n "$(find "$home_dir/bin" -name tlmgr -type f 2> /dev/null | head -n 1)" ]; then
  echo "TinyTeX is already installed in $home_dir; keeping it."
  add_to_path
  exit 0
fi

# shellcheck source=download-cache/cached-download.sh
source "${GHA_CACHED_DOWNLOAD:-$here/../../../download-cache/cached-download.sh}"

asset="TinyTeX-1-${platform}-${version}.tar.xz"
url="https://github.com/rstudio/tinytex-releases/releases/download/${version}/${asset}"
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

cached_download "$url" "$work/$asset" "$want"
if [ "$(_cd_sha256 "$work/$asset")" != "$want" ]; then
  echo "::error::$asset does not match its pinned SHA-256."
  exit 4
fi
# The bundle's top-level directory is .TinyTeX.
parent="$(dirname "$home_dir")"
mkdir -p "$parent"
tar -xJf "$work/$asset" -C "$work"
rm -rf "$home_dir"
mv "$work/.TinyTeX" "$home_dir"
add_to_path
