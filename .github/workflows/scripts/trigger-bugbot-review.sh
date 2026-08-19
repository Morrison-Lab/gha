#!/usr/bin/env bash
# Queue a Cursor Bugbot review for a pull request or merge request.
#
# Wraps POST https://api.cursor.com/bugbot/review
# (https://cursor.com/docs/bugbot.md#trigger-a-review). A 2xx with
# `"outcome":"success"` means the review was queued, not that Bugbot has
# already posted comments; the review itself runs asynchronously.
#
# The API is Enterprise-scoped and needs an API key with admin:* . Team and
# individual installs use the Cursor GitHub App instead of this script.
#
# Env:
#   CURSOR_API_KEY   required. Used as HTTP Basic username with an empty
#                    password. Never printed. Passed to curl via --config,
#                    not on argv.
#   PR_URL           required. Full GitHub PR or GitLab MR URL.
#   DRY_RUN          optional. `true` queues analysis without SCM side
#                    effects. Default false. Still billed, per Cursor's docs.
#   CURSOR_API_BASE  optional. Default https://api.cursor.com
#   CURL_BIN         optional. Default curl. Tests inject a stub here.
#   GITHUB_OUTPUT    optional. When set, also writes request_id= and dry_run=.
#
# Usage: bash trigger-bugbot-review.sh
#
# Output (stdout), one assignment per line so callers can parse by name:
#   request_id=<uuid>
#   dry_run=<true|false>
set -euo pipefail

GITHUB_OUTPUT="${GITHUB_OUTPUT:-/dev/null}"
CURL_BIN="${CURL_BIN:-curl}"
CURSOR_API_BASE="${CURSOR_API_BASE:-https://api.cursor.com}"
PR_URL="${PR_URL:-}"
DRY_RUN="${DRY_RUN:-false}"

if [[ -z "${CURSOR_API_KEY:-}" ]]; then
  echo "::error::CURSOR_API_KEY is not set. The Bugbot review API needs an Enterprise key with admin:* scope. See https://cursor.com/docs/bugbot.md#api" >&2
  exit 1
fi

if [[ -z "$PR_URL" ]]; then
  echo "::error::PR_URL is required (full GitHub pull request or GitLab merge request URL)." >&2
  exit 1
fi

case "$DRY_RUN" in
  true|TRUE|yes|YES|1) dry_json=true ;;
  false|FALSE|no|NO|0|'') dry_json=false ;;
  *)
    echo "::error::DRY_RUN must be true or false; got '$DRY_RUN'." >&2
    exit 1
    ;;
esac

if ! command -v jq >/dev/null 2>&1; then
  echo "::error::jq is required to call the Bugbot review API." >&2
  exit 1
fi

payload="$(jq -cn --arg url "$PR_URL" --argjson dry "$dry_json" \
  '{prUrl: $url, dryRun: $dry}')"

# Basic auth with an empty password, as Cursor's docs show (`-u KEY:`).
# Write headers through --config so the encoded credential is not on
# curl's argv (`ps` / `/proc/<pid>/cmdline`).
auth="$(printf '%s:' "$CURSOR_API_KEY" | base64 | tr -d '\n')"
url="${CURSOR_API_BASE%/}/bugbot/review"
body_file="$(mktemp)"
curl_cfg="$(mktemp)"
chmod 600 "$curl_cfg"
trap 'rm -f "$body_file" "$curl_cfg"' EXIT
cat > "$curl_cfg" <<EOF
header = "Authorization: Basic ${auth}"
header = "Content-Type: application/json"
EOF

set +e
http_code="$("$CURL_BIN" -sS -o "$body_file" -w "%{http_code}" \
  --config "$curl_cfg" \
  --data "$payload" \
  "$url")"
curl_status=$?
set -e

if [[ "$curl_status" -ne 0 ]]; then
  echo "::error::Bugbot review request failed to reach ${CURSOR_API_BASE%/} (curl exit $curl_status)." >&2
  exit 1
fi

body="$(cat "$body_file")"
# Keep a short slice for diagnostics; do not dump unbounded API text.
# A pipe through `head -c` can SIGPIPE under `pipefail` (gha#361); slice in
# bash instead.
body_slice="${body:0:2048}"

if [[ ! "$http_code" =~ ^2[0-9][0-9]$ ]]; then
  api_message="$(printf '%s' "$body" | jq -r '.message // empty' 2>/dev/null || true)"
  if [[ -n "$api_message" ]]; then
    echo "::error::Bugbot review request failed (HTTP $http_code): $api_message" >&2
  else
    echo "::error::Bugbot review request failed (HTTP $http_code)." >&2
    if [[ -n "$body_slice" ]]; then
      echo "::error::$body_slice" >&2
    fi
  fi
  exit 1
fi

outcome="$(printf '%s' "$body" | jq -r '.outcome // empty')"
request_id="$(printf '%s' "$body" | jq -r '.request_id // empty')"
# jq's `//` treats JSON false as empty, so `.dry_run // empty` drops
# `"dry_run": false` and we would fall back to the locally requested
# value. Distinguish absent from false.
dry_out="$(printf '%s' "$body" | jq -r 'if .dry_run == null then empty else (.dry_run | tostring) end')"

if [[ "$outcome" != "success" ]]; then
  api_message="$(printf '%s' "$body" | jq -r '.message // empty')"
  echo "::error::Bugbot review was not queued (outcome=${outcome:-empty}): ${api_message:-no message}" >&2
  exit 1
fi

if [[ -z "$request_id" ]]; then
  echo "::error::Bugbot review reported success but returned no request_id." >&2
  exit 1
fi

if [[ -z "$dry_out" ]]; then
  dry_out="$dry_json"
fi

echo "request_id=$request_id"
echo "dry_run=$dry_out"
{
  echo "request_id=$request_id"
  echo "dry_run=$dry_out"
} >> "$GITHUB_OUTPUT"
