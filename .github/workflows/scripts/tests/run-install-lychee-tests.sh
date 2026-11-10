#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Offline tests for install-lychee.sh, with a stub curl.
# A fake version and a fake archive in a temporary cache stand in for a release,
# because the real pin's file cannot be built here.
set -uo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$repo/.github/workflows/scripts/install-lychee.sh"
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

# The stub curl records its calls and fails, so a download is visible.
bin="$tmp/bin"
mkdir -p "$bin" "$tmp/cache" "$tmp/pkg/lychee-x86_64-unknown-linux-gnu"
cat > "$bin/curl" << 'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$CALLS"
exit 22
EOF
chmod +x "$bin/curl"

# Build a fake release: an archive holding a lychee script, its digest, and the cache name.
printf '#!/bin/sh\necho "lychee 9.9.9"\n' > "$tmp/pkg/lychee-x86_64-unknown-linux-gnu/lychee"
chmod +x "$tmp/pkg/lychee-x86_64-unknown-linux-gnu/lychee"
tar -czf "$tmp/asset.tgz" -C "$tmp/pkg" lychee-x86_64-unknown-linux-gnu
sum="$(sha256sum "$tmp/asset.tgz" | cut -d' ' -f1)"
printf '9.9.9 x86_64 %s\n' "$sum" > "$tmp/pins.txt"
url="https://github.com/lycheeverse/lychee/releases/download/lychee-v9.9.9/lychee-x86_64-unknown-linux-gnu.tar.gz"
key="$(printf '%s' "$url" | sha256sum | cut -c1-16)"
cached="$tmp/cache/$key-lychee-x86_64-unknown-linux-gnu.tar.gz"

run() {
  : > "$tmp/calls"
  rm -rf "$tmp/dest"
  env PATH="$bin:$PATH" CALLS="$tmp/calls" \
    GHA_RELEASE_CACHE_DIR="$tmp/cache" INSTALL_LYCHEE_PINS="$tmp/pins.txt" \
    INSTALL_LYCHEE_DIR="$tmp/dest" INSTALL_LYCHEE_OS=Linux INSTALL_LYCHEE_ARCH=x86_64 \
    "$@" bash "$script" > "$tmp/out" 2>&1
}

# 1. A cached copy that matches the pin installs without any download.
cp "$tmp/asset.tgz" "$cached"
run LYCHEE_VERSION=v9.9.9
check "cached copy installs" 0 "$?"
check "cached copy puts the binary in place" 1 "$([ -x "$tmp/dest/lychee" ] && echo 1 || echo 0)"
check "cached copy needs no download" 0 "$(grep -c '^curl' "$tmp/calls")"

# 2. A corrupt cached copy is not used; the download is tried (and fails here).
printf 'corrupt\n' > "$cached"
run LYCHEE_VERSION=9.9.9
code=$?
check "corrupt copy is not installed" 0 "$([ -e "$tmp/dest/lychee" ] && echo 1 || echo 0)"
check "corrupt copy falls through to a download" 1 "$([ "$(grep -c '^curl' "$tmp/calls")" -ge 1 ] && echo 1 || echo 0)"
check "failed download exits 22" 22 "$code"

# 3. A version with no pin hands over to lychee-action (exit 3).
run LYCHEE_VERSION=1.0.0
check "unpinned version exits 3" 3 "$?"

# 4. Another operating system or architecture hands over (exit 3).
cp "$tmp/asset.tgz" "$cached"
run LYCHEE_VERSION=9.9.9 INSTALL_LYCHEE_OS=Darwin
check "other OS exits 3" 3 "$?"
run LYCHEE_VERSION=9.9.9 INSTALL_LYCHEE_ARCH=riscv64
check "other architecture exits 3" 3 "$?"

# 5. The real pins file has a digest for the default version on each architecture.
for arch in x86_64 aarch64; do
  check "real pin for 0.24.2 $arch" 1 \
    "$(grep -c "^0.24.2 $arch [0-9a-f]\{64\}\$" "$repo/.github/workflows/scripts/install-lychee-pins.txt")"
done

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
