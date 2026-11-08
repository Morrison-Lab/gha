#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Offline tests for install-tinytex.sh, with a fake bundle in a temporary cache.
# A fake version and a fake .tar.xz stand in for a release,
# because the real bundle is 53 MB.
set -uo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
script="$repo/.github/workflows/scripts/install-tinytex.sh"
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

bin="$tmp/bin"
mkdir -p "$bin" "$tmp/cache" "$tmp/src/.TinyTeX/bin/x86_64-linux"
cat > "$bin/curl" << 'EOF'
#!/usr/bin/env bash
echo "curl $*" >> "$CALLS"
exit 22
EOF
chmod +x "$bin/curl"

# Build a fake bundle with the real layout: a .TinyTeX directory holding bin/<arch>/tlmgr.
printf '#!/bin/sh\n' > "$tmp/src/.TinyTeX/bin/x86_64-linux/tlmgr"
chmod +x "$tmp/src/.TinyTeX/bin/x86_64-linux/tlmgr"
tar -cJf "$tmp/asset" -C "$tmp/src" .TinyTeX
sum="$(sha256sum "$tmp/asset" | cut -d' ' -f1)"
printf 'v9.9 linux-x86_64 %s\n' "$sum" > "$tmp/pins.txt"
url="https://github.com/rstudio/tinytex-releases/releases/download/v9.9/TinyTeX-1-linux-x86_64-v9.9.tar.xz"
key="$(printf '%s' "$url" | sha256sum | cut -c1-16)"
cached="$tmp/cache/$key-TinyTeX-1-linux-x86_64-v9.9.tar.xz"

run() {
  : > "$tmp/calls"
  : > "$tmp/path"
  env PATH="$bin:$PATH" CALLS="$tmp/calls" GITHUB_PATH="$tmp/path" \
    GHA_RELEASE_CACHE_DIR="$tmp/cache" INSTALL_TINYTEX_PINS="$tmp/pins.txt" \
    INSTALL_TINYTEX_PLATFORM=Linux-x86_64 TINYTEX_HOME="$tmp/home/.TinyTeX" \
    "$@" bash "$script" > "$tmp/out" 2>&1
}

# 1. A cached copy that matches the pin installs without any download.
cp "$tmp/asset" "$cached"
run
check "cached copy installs" 0 "$?"
check "cached copy needs no download" 0 "$(grep -c '^curl' "$tmp/calls")"
check "tlmgr is unpacked" 1 "$([ -x "$tmp/home/.TinyTeX/bin/x86_64-linux/tlmgr" ] && echo 1 || echo 0)"
check "bin directory goes on PATH" "$tmp/home/.TinyTeX/bin/x86_64-linux" "$(cat "$tmp/path")"

# 2. An existing install is kept and nothing is fetched.
rm -f "$cached"
run
check "existing install exits 0" 0 "$?"
check "existing install needs no download" 0 "$(grep -c '^curl' "$tmp/calls")"
check "existing install is put on PATH" "$tmp/home/.TinyTeX/bin/x86_64-linux" "$(cat "$tmp/path")"
rm -rf "$tmp/home"

# 3. A corrupt cached copy is not used; the download is tried (and fails here).
printf 'corrupt\n' > "$cached"
run
code=$?
check "corrupt copy installs nothing" 0 "$([ -e "$tmp/home/.TinyTeX" ] && echo 1 || echo 0)"
check "corrupt copy falls through to a download" 1 "$([ "$(grep -c '^curl' "$tmp/calls")" -ge 1 ] && echo 1 || echo 0)"
check "failed download exits 22" 22 "$code"

# 4. A version with no pin hands over (exit 3).
run TINYTEX_VERSION=v0.0
check "unpinned version exits 3" 3 "$?"

# 5. Another platform hands over (exit 3).
run INSTALL_TINYTEX_PLATFORM=Darwin-arm64
check "other platform exits 3" 3 "$?"

# 6. The real pins file has a digest for its default version.
check "real pin" 1 "$(grep -c '^v[0-9.]* linux-x86_64 [0-9a-f]\{64\}$' "$repo/.github/workflows/scripts/install-tinytex-pins.txt")"

echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ]
