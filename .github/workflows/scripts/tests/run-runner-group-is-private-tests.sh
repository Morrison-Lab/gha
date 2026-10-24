#!/usr/bin/env bash
# Exercises scripts/runner-group-is-private.sh offline against runner-group
# JSON. The refusals are the cases to keep: accepting a group that can admit a
# public repository lets a fork's pull request run code on the lab machine.
#
# Usage: bash .github/workflows/scripts/tests/run-runner-group-is-private-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
guard="$repo_root/scripts/runner-group-is-private.sh"

failures=0
cases=0

# run <name> <accept|refuse> <group json>
run() {
  local name="$1" want="$2" json="$3" got=refuse
  cases=$((cases + 1))
  if bash "$guard" <<< "$json" 2> /dev/null; then got=accept; fi
  if [[ "$got" != "$want" ]]; then
    echo "::error::$name: expected $want but got $got"
    failures=$((failures + 1))
  fi
}

run "all + public false" accept '{"visibility":"all","allows_public_repositories":false}'
run "selected + public false" accept '{"visibility":"selected","allows_public_repositories":false}'
run "private + public false" accept '{"visibility":"private","allows_public_repositories":false}'
run "all + inherited null" accept '{"visibility":"all","allows_public_repositories":false,"inherited_allows_public_repositories":null}'
run "all + public true" refuse '{"visibility":"all","allows_public_repositories":true}'
run "selected + public true" refuse '{"visibility":"selected","allows_public_repositories":true}'
run "all + public missing" refuse '{"visibility":"all"}'
run "all + public null" refuse '{"visibility":"all","allows_public_repositories":null}'
run "all + public string false" refuse '{"visibility":"all","allows_public_repositories":"false"}'
run "all + public zero" refuse '{"visibility":"all","allows_public_repositories":0}'
run "all + inherited true" refuse '{"visibility":"all","allows_public_repositories":false,"inherited_allows_public_repositories":true}'
run "all + inherited string" refuse '{"visibility":"all","allows_public_repositories":false,"inherited_allows_public_repositories":"false"}'
run "empty input" refuse ''
run "not json" refuse 'oops'

echo "$cases cases, $failures failures"
[[ "$failures" -eq 0 ]]
