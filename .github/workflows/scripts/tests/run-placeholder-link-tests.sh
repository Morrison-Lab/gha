#!/usr/bin/env bash
# Tests for the prior-verdict link rewrite in claude-code-review.yml's
# "Post review comment" step (gha#1766). The step runs in the caller's
# checkout, so the rewrite is inline there; this suite extracts the lines
# between its begin and end markers and runs them against a stub `gh`.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
WORKFLOW="$ROOT/.github/workflows/claude-code-review.yml"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# Strip the YAML block indentation from the marked lines.
sed -n '/# placeholder-link rewrite begin/,/# placeholder-link rewrite end/p' "$WORKFLOW" \
  | sed -E 's/^ {10}//' > "$TMP/rewrite.sh"
if ! grep -q 'PLACEHOLDER_RE=' "$TMP/rewrite.sh"; then
  echo "::error::could not extract the rewrite block from $WORKFLOW"
  exit 1
fi

mkdir -p "$TMP/bin"
cat > "$TMP/bin/gh" <<'EOF'
#!/usr/bin/env bash
# Stub: print the URLs in $STUB_URLS one per line, or fail when asked.
[ "${STUB_FAIL:-}" = 1 ] && exit 1
printf '%s' "${STUB_URLS:-}"
EOF
chmod +x "$TMP/bin/gh"

fails=0
run_case() {
  local name="$1" review="$2" expect="$3" urls="${4:-}" stub_fail="${5:-}"
  local got
  got="$(PATH="$TMP/bin:$PATH" STUB_URLS="$urls" STUB_FAIL="$stub_fail" \
    REVIEW="$review" REPO=o/r PR_NUMBER=7 \
    bash -c 'set -uo pipefail; source "$1" >/dev/null; printf "%s" "$REVIEW"' _ "$TMP/rewrite.sh")"
  if [ "$got" = "$expect" ]; then
    echo "ok   $name"
  else
    echo "::error::$name: expected [$expect], got [$got]"
    fails=$((fails + 1))
  fi
}

PRIOR=https://github.com/o/r/pull/7#issuecomment-111
NEWER=https://github.com/o/r/pull/7#issuecomment-222
two_urls="$PRIOR"$'\n'"$NEWER"$'\n'

run_case "absolute placeholder becomes the newest prior verdict" \
  "see https://github.com/o/r/pull/7#issuecomment-placeholder, posted" \
  "see $NEWER, posted" "$two_urls"
run_case "markdown link target is rewritten, brackets kept" \
  "[prior](https://github.com/o/r/pull/7#issuecomment-placeholder)." \
  "[prior]($NEWER)." "$two_urls"
run_case "relative fragment is rewritten" \
  "[prior](#issuecomment-PLACEHOLDER)" "[prior]($NEWER)" "$two_urls"
run_case "a real numeric comment link is left alone" \
  "see $PRIOR and done" "see $PRIOR and done" "$two_urls"
run_case "no prior verdict falls back to the PR" \
  "see #issuecomment-xyz now" "see https://github.com/o/r/pull/7 now" ""
run_case "an API failure falls back to the PR" \
  "see #issuecomment-xyz now" "see https://github.com/o/r/pull/7 now" "$two_urls" 1
run_case "text with no comment link is unchanged" \
  "Ready for merge." "Ready for merge." "$two_urls"

if [ "$fails" -gt 0 ]; then
  echo "::error::$fails placeholder-link case(s) failed"
  exit 1
fi
echo "All placeholder-link cases passed."
