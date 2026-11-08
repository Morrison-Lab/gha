#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
#
# Download a release archive, through a group-share cache when one is mounted.
#
# Source this file, then call:
#
#   cached_download URL OUTPUT_PATH [EXPECTED_SHA256]
#
# The cache directory is GHA_RELEASE_CACHE_DIR, or the Morrison-Lab cluster
# share when that directory exists.
# A runner that cannot see the share downloads exactly as before.
#
# A cached file is used only when EXPECTED_SHA256 is given and matches.
# A downloaded file is stored only when EXPECTED_SHA256 is given and matches,
# so the cache never holds a file nobody checked.
# A cache that cannot be read or written is skipped with a notice and never
# fails the job.

: "${GHA_RELEASE_CACHE_DIR:=/cluster/research-groups/morrison/ci/release-cache}"

_cd_sha256() {
  if command -v sha256sum > /dev/null 2>&1; then
    sha256sum "$1" | cut -d' ' -f1
  else
    shasum -a 256 "$1" | cut -d' ' -f1
  fi
}

# One file name per URL, so two releases of one tool never collide.
_cd_cache_path() {
  local url="$1" key
  key="$(printf '%s' "$url" | _cd_sha256 /dev/stdin | cut -c1-16)"
  printf '%s/%s-%s' "$GHA_RELEASE_CACHE_DIR" "$key" "$(basename "$url")"
}

cached_download() {
  local url="$1" out="$2" want="${3:-}" cached="" tmp=""
  if [ -n "$want" ] && [ -d "$GHA_RELEASE_CACHE_DIR" ]; then
    cached="$(_cd_cache_path "$url")"
    if [ -f "$cached" ] && [ "$(_cd_sha256 "$cached")" = "$want" ]; then
      echo "Using cached $(basename "$url") from $GHA_RELEASE_CACHE_DIR"
      cp "$cached" "$out"
      return 0
    fi
  fi

  curl --fail --silent --show-error --location \
    --retry 8 --retry-delay 10 --retry-all-errors \
    --output "$out" "$url" || return $?

  if [ -n "$cached" ] && [ -w "$GHA_RELEASE_CACHE_DIR" ] &&
    [ "$(_cd_sha256 "$out")" = "$want" ]; then
    tmp="$(mktemp "$GHA_RELEASE_CACHE_DIR/.part.XXXXXX")" || tmp=""
    if [ -n "$tmp" ] && cp "$out" "$tmp" && mv -f "$tmp" "$cached"; then
      echo "Stored $(basename "$url") in $GHA_RELEASE_CACHE_DIR"
    else
      rm -f "$tmp"
      echo "::notice::Could not write $GHA_RELEASE_CACHE_DIR; continuing without the cache."
    fi
  fi
  return 0
}
