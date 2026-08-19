#!/usr/bin/env bash
# Exercises trigger-bugbot-review.sh offline with a stub curl, so CI never
# calls api.cursor.com and never needs CURSOR_API_KEY.
#
# Usage: bash .github/workflows/scripts/tests/run-trigger-bugbot-review-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
trigger="$repo_root/.github/workflows/scripts/trigger-bugbot-review.sh"

failures=0
total=0
stub_dir="$(mktemp -d)"
trap 'rm -rf "$stub_dir"' EXIT

install_stub() {
  local http_code="$1" body="$2" curl_exit="${3:-0}"
  cat > "$stub_dir/curl" <<EOF
#!/usr/bin/env bash
set -euo pipefail
outfile=""
data=""
while [[ \$# -gt 0 ]]; do
  case "\$1" in
    -o) outfile="\$2"; shift 2 ;;
    -w) shift 2 ;;
    --data) data="\$2"; shift 2 ;;
    --header) shift 2 ;;
    -sS) shift ;;
    *) shift ;;
  esac
done
printf '%s' "\$data" > "$stub_dir/last-data"
if [[ "$curl_exit" -ne 0 ]]; then
  exit $curl_exit
fi
if [[ -n "\$outfile" ]]; then
  cat > "\$outfile" <<'BODY'
$body
BODY
fi
printf '%s' "$http_code"
EOF
  chmod +x "$stub_dir/curl"
}

ok() {
  total=$((total + 1))
  echo "OK   $1"
}

fail() {
  total=$((total + 1))
  echo "::error::$1"
  failures=$((failures + 1))
}

success_body='{"outcome":"success","message":"Bugbot review queued","request_id":"6e0d261c-86a2-4383-89f0-9162c1c10662","dry_run":false}'
dry_body='{"outcome":"success","message":"Bugbot dry-run review queued","request_id":"aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee","dry_run":true}'
disabled_body='{"outcome":"error","message":"Bugbot is disabled for this repository"}'
auth_body='{"outcome":"error","message":"Unauthorized"}'

set +e
env -u CURSOR_API_KEY PR_URL="https://github.com/Morrison-Lab/gha/pull/1" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'CURSOR_API_KEY is not set' "$stub_dir/err"; then
  ok "missing CURSOR_API_KEY fails"
else
  fail "missing CURSOR_API_KEY: expected exit 1 with a named error (exit $status)"
fi

set +e
CURSOR_API_KEY="test-key" PR_URL="" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'PR_URL is required' "$stub_dir/err"; then
  ok "missing PR_URL fails"
else
  fail "missing PR_URL: expected exit 1 (exit $status)"
fi

install_stub 200 "$success_body"
out="$(CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger")"
if echo "$out" | grep -qx 'request_id=6e0d261c-86a2-4383-89f0-9162c1c10662' \
  && echo "$out" | grep -qx 'dry_run=false' \
  && grep -q '"prUrl":"https://github.com/Morrison-Lab/gha/pull/42"' "$stub_dir/last-data" \
  && grep -q '"dryRun":false' "$stub_dir/last-data"; then
  ok "success queue writes request_id and posts prUrl"
else
  fail "success queue did not write the expected request_id / payload"
  echo "$out"
  cat "$stub_dir/last-data" || true
fi

if echo "$out" | grep -q 'test-key'; then
  fail "CURSOR_API_KEY leaked to stdout"
else
  ok "API key is not printed on success"
fi

install_stub 200 "$dry_body"
out="$(CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  DRY_RUN=true \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger")"
if echo "$out" | grep -qx 'dry_run=true' \
  && grep -q '"dryRun":true' "$stub_dir/last-data"; then
  ok "DRY_RUN=true is sent and reported"
else
  fail "dry-run did not set dryRun true in the request or output"
  echo "$out"
  cat "$stub_dir/last-data" || true
fi

install_stub 400 "$disabled_body"
set +e
CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'Bugbot is disabled for this repository' "$stub_dir/err"; then
  ok "HTTP 400 disabled-repo surfaces the API message"
else
  fail "HTTP 400 did not fail with the API message (exit $status)"
  cat "$stub_dir/err"
fi

install_stub 401 "$auth_body"
set +e
CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'HTTP 401' "$stub_dir/err"; then
  ok "HTTP 401 fails"
else
  fail "HTTP 401 did not fail (exit $status)"
fi

install_stub 000 "" 7
set +e
CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'failed to reach' "$stub_dir/err"; then
  ok "curl transport failure is reported"
else
  fail "curl exit 7 was not reported (exit $status)"
  cat "$stub_dir/err"
fi

install_stub 200 "$disabled_body"
set +e
CURSOR_API_KEY="test-key" PR_URL="https://github.com/Morrison-Lab/gha/pull/42" \
  CURL_BIN="$stub_dir/curl" CURSOR_API_BASE="https://api.example.invalid" \
  bash "$trigger" >"$stub_dir/out" 2>"$stub_dir/err"
status=$?
set -e
if [[ "$status" -ne 0 ]] && grep -q 'was not queued' "$stub_dir/err"; then
  ok "2xx with outcome=error still fails"
else
  fail "2xx error outcome was treated as success (exit $status)"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total trigger-bugbot-review case(s) did not behave as expected"
  exit 1
fi
echo "All $total trigger-bugbot-review cases behaved as expected."
