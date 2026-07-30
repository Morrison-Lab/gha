#!/usr/bin/env bash
#
# Install a pinned gitleaks release into GITLEAKS_BIN_DIR.
#
# The official `gitleaks/gitleaks-action` is not used: its action.yml carries a
# commercial EULA header, and its README states GITLEAKS_LICENSE is "required
# for organizations", which every consumer of this repo is. The gitleaks CLI
# itself is MIT, so the release binary is installed directly.
#
# Integrity comes from one pinned constant. The release's own checksums file is
# fetched and compared against GITLEAKS_CHECKSUMS_SHA256; only then is it
# trusted to verify the platform tarball. Pinning the checksums file rather
# than each tarball keeps a single value covering every architecture.
set -euo pipefail

: "${GITLEAKS_VERSION:?GITLEAKS_VERSION is required}"
: "${GITLEAKS_CHECKSUMS_SHA256:?GITLEAKS_CHECKSUMS_SHA256 is required}"
: "${GITLEAKS_BIN_DIR:?GITLEAKS_BIN_DIR is required}"

case "$(uname -s)" in
  Linux) os=linux ;;
  Darwin) os=darwin ;;
  *)
    echo "::error::check-secrets: unsupported operating system '$(uname -s)'." >&2
    exit 1
    ;;
esac

case "$(uname -m)" in
  x86_64 | amd64) arch=x64 ;;
  aarch64 | arm64) arch=arm64 ;;
  *)
    echo "::error::check-secrets: unsupported architecture '$(uname -m)'." >&2
    exit 1
    ;;
esac

base_url="https://github.com/gitleaks/gitleaks/releases/download/v${GITLEAKS_VERSION}"
checksums_file="gitleaks_${GITLEAKS_VERSION}_checksums.txt"
tarball="gitleaks_${GITLEAKS_VERSION}_${os}_${arch}.tar.gz"

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

curl --fail --silent --show-error --location --retry 3 --retry-delay 2 \
  --output "$work_dir/$checksums_file" "$base_url/$checksums_file"

actual_checksums_sha256="$(sha256sum "$work_dir/$checksums_file" | cut -d' ' -f1)"
if [ "$actual_checksums_sha256" != "$GITLEAKS_CHECKSUMS_SHA256" ]; then
  echo "::error::check-secrets: $checksums_file failed its integrity check." >&2
  echo "  expected: $GITLEAKS_CHECKSUMS_SHA256" >&2
  echo "  actual:   $actual_checksums_sha256" >&2
  echo "  If you just bumped the 'version' input, update 'checksums-sha256' too." >&2
  exit 1
fi

curl --fail --silent --show-error --location --retry 3 --retry-delay 2 \
  --output "$work_dir/$tarball" "$base_url/$tarball"

# grep exits 1 when the platform's entry is absent, which is a real failure
# rather than an expected empty result -- report it rather than letting an
# empty checksum file silently verify nothing.
if ! grep -F " ${tarball}" "$work_dir/$checksums_file" > "$work_dir/expected.sha256"; then
  echo "::error::check-secrets: no checksum entry for $tarball in $checksums_file." >&2
  exit 1
fi

(cd "$work_dir" && sha256sum --check --status expected.sha256) || {
  echo "::error::check-secrets: $tarball failed its checksum verification." >&2
  exit 1
}

mkdir -p "$GITLEAKS_BIN_DIR"
tar -xzf "$work_dir/$tarball" -C "$GITLEAKS_BIN_DIR" gitleaks
chmod +x "$GITLEAKS_BIN_DIR/gitleaks"

echo "Installed $("$GITLEAKS_BIN_DIR/gitleaks" version) into $GITLEAKS_BIN_DIR"
