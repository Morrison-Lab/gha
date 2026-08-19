#!/usr/bin/env bash
# Stub curl for _selftest.yml's trigger-bugbot-review e2e step.
# Writes a canned Bugbot success body to -o and prints HTTP 200.
# No network, no credentials.
set -euo pipefail
outfile=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    -o) outfile="$2"; shift 2 ;;
    -w) shift 2 ;;
    *) shift ;;
  esac
done
if [[ -n "$outfile" ]]; then
  printf '%s' '{"outcome":"success","message":"Bugbot review queued","request_id":"selftest-request-id","dry_run":false}' > "$outfile"
fi
printf '%s' '200'
