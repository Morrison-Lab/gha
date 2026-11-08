#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Offline tests for install-quarto.sh, with stub sudo, dpkg and quarto.
# A fake version and a fake .deb in a temporary cache stand in for a release,
# because the real pin's file cannot be built here.
set -uo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$repo/.github/workflows/scripts/install-quarto.sh"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT

pass=0
fail=0
check() {
  if [ "$2" = "$3" ]; then
    pass=$((pass + 1))
  else
    fail=$((fail + 1))
    echo "FAIL: $1 (wanted '$2', got '$3')"
  fi
}

# Stub tools record their calls; sudo passes through unless NO_SUDO is set.
bin="$tmp/bin"
mkdir -p "$bin" "$tmp/cache"
cat > "$bin/sudo" << 'EOF'
#!/usr/bin/env bash
[ -n "${NO_SUDO:-}" ] && exit 1
[ "$1" = "-n" ] && shift
[ "$1" = "true" ] && exit 0
exec "$@"
EOF
cat > "$bin/dpkg" << 'EOF'
#!/usr/bin/env bash
echo "dpkg $*" >> "$CALLS"
EOF
cat > "$bin/quarto" << 'EOF'
#!/usr/bin/env bash
echo "9.9.9"
EOF
cat > "$bin/curl" << 'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$CALLS"
exit 22
EOF
chmod +x "$bin"/*

# Build a fake release: a file, its digest, and where the cache names it.
printf 'fake deb\n' > "$tmp/asset"
sum="$(sha256sum "$tmp/asset" | cut -d' ' -f1)"
printf '9.9.9 linux-amd64 %s\n' "$sum" > "$tmp/pins.txt"
url="https://github.com/quarto-dev/quarto-cli/releases/download/v9.9.9/quarto-9.9.9-linux-amd64.deb"
key="$(printf '%s' "$url" | sha256sum | cut -c1-16)"

run() {
  : > "$tmp/calls"
  env PATH="$bin:$PATH" CALLS="$tmp/calls" \
    GHA_RELEASE_CACHE_DIR="$tmp/cache" INSTALL_QUARTO_PINS="$tmp/pins.txt" \
    INSTALL_QUARTO_PLATFORM=Linux-x86_64 "$@" bash "$script" > "$tmp/out" 2>&1
}

# 1. A cached copy that matches the pin installs without any download.
cp "$tmp/asset" "$tmp/cache/$key-quarto-9.9.9-linux-amd64.deb"
run QUARTO_VERSION=9.9.9
check "cached copy installs" 0 "$?"
check "cached copy runs dpkg" 1 "$(grep -c '^dpkg -i' "$tmp/calls")"
check "cached copy needs no download" 0 "$(grep -c '^curl' "$tmp/calls")"

# 2. A corrupt cached copy is not used; the download is tried (and fails here).
printf 'corrupt\n' > "$tmp/cache/$key-quarto-9.9.9-linux-amd64.deb"
run QUARTO_VERSION=9.9.9
code=$?
check "corrupt copy is not installed" 0 "$(grep -c '^dpkg' "$tmp/calls")"
check "corrupt copy falls through to a download" 1 "$([ "$(grep -c '^curl' "$tmp/calls")" -ge 1 ] && echo 1 || echo 0)"
# A failed download is exit 22 from curl, which the action treats as a failure, not a hand-over.
check "failed download exits 22" 22 "$code"

# 3. A version with no pin hands over to the setup action (exit 3).
run QUARTO_VERSION=1.0.0
check "unpinned version exits 3" 3 "$?"

# 4. No passwordless sudo hands over (exit 3), and nothing is installed.
cp "$tmp/asset" "$tmp/cache/$key-quarto-9.9.9-linux-amd64.deb"
run QUARTO_VERSION=9.9.9 NO_SUDO=1
check "no sudo exits 3" 3 "$?"
check "no sudo installs nothing" 0 "$(grep -c '^dpkg' "$tmp/calls")"

# 5. Another platform hands over (exit 3).
run QUARTO_VERSION=9.9.9 INSTALL_QUARTO_PLATFORM=Darwin-arm64
check "other platform exits 3" 3 "$?"

# 6. The real pins file has a digest for the default version.
check "real pin for 1.11.9" 1 "$(grep -c '^1.11.9 linux-amd64 [0-9a-f]\{64\}$' "$repo/.github/workflows/scripts/install-quarto-pins.txt")"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
