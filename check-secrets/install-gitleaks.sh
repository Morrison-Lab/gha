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

# macOS runners ship `shasum` rather than GNU coreutils' `sha256sum`, so the
# Darwin branch above would otherwise promise support the script cannot honour.
sha256_of() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

work_dir="$(mktemp -d)"
trap 'rm -rf "$work_dir"' EXIT

# --retry-all-errors (curl 7.71+) also retries connection resets, which the
# plain --retry list (408, 429, 500, 502, 503, 504, timeouts) does not.
# v2 callers may run older curl on self-hosted runners, where the unknown
# flag would fail the download outright, so pass it only when supported.
retry_all_errors=()
# Capture the help text rather than piping it to grep -q: under pipefail an
# early grep exit can SIGPIPE curl and read as "unsupported".
if curl_help="$(curl --help all 2>/dev/null)" \
  && [[ "$curl_help" == *--retry-all-errors* ]]; then
  retry_all_errors=(--retry-all-errors)
fi

curl --fail --silent --show-error --location --retry 8 --retry-delay 10 ${retry_all_errors[@]+"${retry_all_errors[@]}"} \
  --output "$work_dir/$checksums_file" "$base_url/$checksums_file"

actual_checksums_sha256="$(sha256_of "$work_dir/$checksums_file")"
if [ "$actual_checksums_sha256" != "$GITLEAKS_CHECKSUMS_SHA256" ]; then
  echo "::error::check-secrets: $checksums_file failed its integrity check." >&2
  echo "  expected: $GITLEAKS_CHECKSUMS_SHA256" >&2
  echo "  actual:   $actual_checksums_sha256" >&2
  echo "  If you just bumped the 'version' input, update 'checksums-sha256' too." >&2
  exit 1
fi

curl --fail --silent --show-error --location --retry 8 --retry-delay 10 ${retry_all_errors[@]+"${retry_all_errors[@]}"} \
  --output "$work_dir/$tarball" "$base_url/$tarball"

# Match the filename as a whole field rather than as a substring, and make a
# missing entry a loud failure: an empty expected value would otherwise compare
# equal to nothing and verify nothing.
expected_tarball_sha256="$(
  awk -v want="$tarball" '$2 == want { print $1; found = 1 } END { exit !found }' \
    "$work_dir/$checksums_file"
)" || {
  echo "::error::check-secrets: no checksum entry for $tarball in $checksums_file." >&2
  exit 1
}

actual_tarball_sha256="$(sha256_of "$work_dir/$tarball")"
if [ "$actual_tarball_sha256" != "$expected_tarball_sha256" ]; then
  echo "::error::check-secrets: $tarball failed its checksum verification." >&2
  echo "  expected: $expected_tarball_sha256" >&2
  echo "  actual:   $actual_tarball_sha256" >&2
  exit 1
fi

mkdir -p "$GITLEAKS_BIN_DIR"
tar -xzf "$work_dir/$tarball" -C "$GITLEAKS_BIN_DIR" gitleaks
chmod +x "$GITLEAKS_BIN_DIR/gitleaks"

echo "Installed $("$GITLEAKS_BIN_DIR/gitleaks" version) into $GITLEAKS_BIN_DIR"
