#!/usr/bin/env bash
#
# Install a pinned crate-ci/typos release into TYPOS_BIN_DIR.
#
# The official `crate-ci/typos` GitHub Action is not used: it scans the whole
# tree and has no line-level diff filter, which is the adoption problem this
# capability exists to solve. The CLI is MIT and ships GitHub-release
# tarballs, so the binary is installed directly -- the same reason
# check-secrets wraps the gitleaks CLI rather than gitleaks/gitleaks-action.
#
# Integrity is one pinned SHA-256 of the platform tarball (the default is
# linux x86_64 musl, which is what `ubuntu-latest` fetches). Bumping
# `version` requires bumping `checksums-sha256` to match that version's
# tarball for the runner you are on.
set -euo pipefail

: "${TYPOS_VERSION:?TYPOS_VERSION is required}"
: "${TYPOS_CHECKSUMS_SHA256:?TYPOS_CHECKSUMS_SHA256 is required}"
: "${TYPOS_BIN_DIR:?TYPOS_BIN_DIR is required}"

# Strip a leading v so either '1.49.0' or 'v1.49.0' works; the release
# asset names always include the v.
ver="${TYPOS_VERSION#v}"

case "$(uname -s)" in
  Linux) os=unknown-linux-musl ;;
  Darwin) os=apple-darwin ;;
  *)
    echo "::error::check-typos: unsupported operating system '$(uname -s)'." >&2
    exit 1
    ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) arch=x86_64 ;;
  aarch64 | arm64) arch=aarch64 ;;
  *)
    echo "::error::check-typos: unsupported architecture '$(uname -m)'." >&2
    exit 1
    ;;
esac

tarball="typos-v${ver}-${arch}-${os}.tar.gz"
base_url="https://github.com/crate-ci/typos/releases/download/v${ver}"

# macOS runners ship `shasum` rather than GNU coreutils' `sha256sum`.
sha256_of() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl --fail --silent --show-error --location --retry 3 --retry-delay 2 \
  --output "$work_dir/$tarball" "$base_url/$tarball"

actual_sha256="$(sha256_of "$work_dir/$tarball")"
if [ "$actual_sha256" != "$TYPOS_CHECKSUMS_SHA256" ]; then
  echo "::error::check-typos: $tarball failed its checksum verification." >&2
  echo "  expected: $TYPOS_CHECKSUMS_SHA256" >&2
  echo "  actual:   $actual_sha256" >&2
  echo "  If you just bumped the 'version' input, update 'checksums-sha256' too." >&2
  echo "  On a non-x86_64 Linux runner, pass that platform's tarball digest." >&2
  exit 1
fi

# The release tarball members are `./typos` plus licences and docs, not a
# single named file at the archive root -- passing `typos` as a member
# name fails to extract.
tar -xzf "$work_dir/$tarball" -C "$work_dir"
if [ ! -f "$work_dir/typos" ]; then
  echo "::error::check-typos: $tarball did not contain a 'typos' binary." >&2
  exit 1
fi

mkdir -p "$TYPOS_BIN_DIR"
install -m 755 "$work_dir/typos" "$TYPOS_BIN_DIR/typos"

echo "Installed $("$TYPOS_BIN_DIR/typos" --version) into $TYPOS_BIN_DIR"
