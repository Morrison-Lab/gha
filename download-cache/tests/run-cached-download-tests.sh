#!/usr/bin/env bash
# Offline tests for cached-download.sh, using a stub curl that serves a local file.
set -uo pipefail
here="$(cd "$(dirname "$0")" && pwd)"
tmp="$(mktemp -d)"
trap 'rm -rf "$tmp"' EXIT
mkdir -p "$tmp/bin" "$tmp/cache"
printf 'payload\n' > "$tmp/served"
cat > "$tmp/bin/curl" <<'S'
#!/usr/bin/env bash
echo x >> "$STUB_COUNT"
[ -n "${STUB_FAIL:-}" ] && exit 22
while [ $# -gt 0 ]; do [ "$1" = --output ] && out="$2"; shift; done
cp "$STUB_SERVED" "$out"
S
chmod +x "$tmp/bin/curl"
export PATH="$tmp/bin:$PATH" STUB_SERVED="$tmp/served" STUB_COUNT="$tmp/count"
export GHA_RELEASE_CACHE_DIR="$tmp/cache"
# shellcheck disable=SC1091
source "$here/../cached-download.sh"
good="$(_cd_sha256 "$tmp/served")"
fails=0
check() { if [ "$2" != "$3" ]; then echo "FAIL: $1 (got '$2', want '$3')"; fails=$((fails + 1)); fi; }
calls() { if [ -f "$tmp/count" ]; then wc -l < "$tmp/count" | tr -d ' '; else echo 0; fi; }

cached_download https://example.org/a.tgz "$tmp/o1" "$good" > /dev/null
check "first call downloads" "$(calls)" 1
check "first call stores" "$(find "$tmp/cache" -name '*a.tgz' | wc -l | tr -d ' ')" 1
STUB_FAIL=1 cached_download https://example.org/a.tgz "$tmp/o2" "$good" > /dev/null
check "second call needs no download" "$(calls)" 1
check "cached copy is delivered" "$(cat "$tmp/o2")" payload
cached_download https://example.org/b.tgz "$tmp/o3" "deadbeef" > /dev/null
check "wrong digest is never stored" "$(find "$tmp/cache" -name '*b.tgz' | wc -l | tr -d ' ')" 0
cached_download https://example.org/c.tgz "$tmp/o4" > /dev/null
check "no digest is never stored" "$(find "$tmp/cache" -name '*c.tgz' | wc -l | tr -d ' ')" 0
printf 'corrupt\n' > "$(_cd_cache_path https://example.org/a.tgz)"
cached_download https://example.org/a.tgz "$tmp/o5" "$good" > /dev/null
check "corrupt cache entry is replaced" "$(cat "$tmp/o5")" payload
GHA_RELEASE_CACHE_DIR="$tmp/missing" cached_download https://example.org/d.tgz "$tmp/o6" "$good" > /dev/null
check "absent cache directory still downloads" "$(cat "$tmp/o6")" payload
STUB_FAIL=1 cached_download https://example.org/e.tgz "$tmp/o7" "$good" > /dev/null 2>&1
check "failed download fails" "$?" 22

[ "$fails" -eq 0 ] && echo "all passed" || exit 1
