#!/usr/bin/env bash
# Exercises classify-push-failure.sh offline, mirroring the pattern the other
# script suites in this directory use. Wired into _selftest.yml's
# `review-fail-check` job.
#
# Usage: bash .github/workflows/scripts/tests/run-classify-push-failure-tests.sh
set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
classify="$repo_root/.github/workflows/scripts/classify-push-failure.sh"

failures=0
total=0

# The verbatim rejection from the run gha#360 was filed over: a GitHub App
# (the integrated GITHUB_TOKEN) pushing a change under .github/workflows/.
app_rejection=$(cat <<'EOF'
remote: error: GH013: Repository rule violations found for refs/heads/topic.
To https://github.com/Morrison-Lab/ai-config.git
 ! [remote rejected] HEAD -> topic (refusing to allow a GitHub App to create or update workflow `.github/workflows/validate.yml` without `workflows` permission)
error: failed to push some refs to 'https://github.com/Morrison-Lab/ai-config.git'
EOF
)

# GitHub words the tail differently per credential type -- a PAT is rejected
# `without \`workflow\` scope`, not `without \`workflows\` permission` -- which
# is why the matcher keys on the shared "refusing to allow ... to create or
# update workflow" clause instead.
pat_rejection=$(cat <<'EOF'
 ! [remote rejected] main -> main (refusing to allow a Personal Access Token to create or update workflow `.github/workflows/ci.yml` without `workflow` scope)
error: failed to push some refs to 'https://github.com/o/r.git'
EOF
)

oauth_rejection=' ! [remote rejected] HEAD -> b (refusing to allow an OAuth App to create or update workflow `.github/workflows/x.yml` without `workflow` scope)'

non_ff=$(cat <<'EOF'
 ! [rejected]        HEAD -> topic (fetch first)
error: failed to push some refs to 'https://github.com/o/r.git'
hint: Updates were rejected because the remote contains work that you do not
hint: have locally.
EOF
)

non_ff_plain=' ! [rejected]        HEAD -> topic (non-fast-forward)'

protected=$(cat <<'EOF'
remote: error: GH006: Protected branch update failed for refs/heads/main.
remote: error: Required status check "build" is expected.
EOF
)

auth_failure='fatal: Authentication failed for https://github.com/o/r.git/'

# check_kind <name> <log> <expected kind>
check_kind() {
  local name="$1" log="$2" want="$3" got
  total=$((total + 1))
  got="$(printf '%s\n' "$log" | bash "$classify" - | sed -n '1s/^kind=//p')"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name"
  else
    echo "::error::$name: expected kind '$want' but got '$got'"
    failures=$((failures + 1))
  fi
}

# check_advice <name> <log> <substring that must appear> <grep mode: has|lacks>
check_advice() {
  local name="$1" log="$2" needle="$3" mode="${4:-has}" out
  total=$((total + 1))
  out="$(printf '%s\n' "$log" | bash "$classify" -)"
  if [[ "$mode" == "has" ]] && grep -qF -- "$needle" <<<"$out"; then
    echo "OK   $name"
  elif [[ "$mode" == "lacks" ]] && ! grep -qF -- "$needle" <<<"$out"; then
    echo "OK   $name"
  else
    echo "::error::$name: expected output to $mode '$needle'"
    failures=$((failures + 1))
  fi
}

check_kind "GitHub App workflows rejection" "$app_rejection"   workflows-permission
check_kind "PAT workflow-scope rejection"   "$pat_rejection"   workflows-permission
check_kind "OAuth App rejection"            "$oauth_rejection" workflows-permission
check_kind "non-fast-forward (fetch first)" "$non_ff"          non-fast-forward
check_kind "non-fast-forward (plain)"       "$non_ff_plain"    non-fast-forward
check_kind "protected branch"               "$protected"       other
check_kind "authentication failure"         "$auth_failure"    other
check_kind "empty log"                      ""                 other

# The whole point of the workflows-permission branch is naming the secret that
# is missing; a generic failure must NOT name it, or the advice sends a reader
# to configure something unrelated to what actually broke.
check_advice "names WORKFLOW_TOKEN"          "$app_rejection" "WORKFLOW_TOKEN"          has
check_advice "links the README permissions"  "$app_rejection" "gha#permissions"         has
check_advice "generic case omits the secret" "$auth_failure"  "WORKFLOW_TOKEN"          lacks

# The three-part output contract the composite action parses: `kind=` on line
# 1, `headline=` on line 2, a blank line 3, advice from line 4.
total=$((total + 1))
out="$(printf '%s\n' "$app_rejection" | bash "$classify" -)"
if [[ "$(sed -n '1p' <<<"$out")" == kind=* ]] &&
   [[ "$(sed -n '2p' <<<"$out")" == headline=* ]] &&
   [[ -z "$(sed -n '3p' <<<"$out")" ]] &&
   [[ -n "$(tail -n +4 <<<"$out")" ]]; then
  echo "OK   output shape (kind / headline / blank / advice)"
else
  echo "::error::output shape: expected kind, headline, blank line, then advice"
  failures=$((failures + 1))
fi

# The headline reaches an `::error::` annotation, which is a single line.
total=$((total + 1))
if [[ "$(sed -n '2s/^headline=//p' <<<"$out" | wc -l)" -eq 1 ]]; then
  echo "OK   headline is a single line"
else
  echo "::error::headline must be a single line to be usable in ::error::"
  failures=$((failures + 1))
fi

# Reading from a file is the path the composite uses when it is not piping.
total=$((total + 1))
tmp_log="$(mktemp)"
printf '%s\n' "$app_rejection" > "$tmp_log"
if [[ "$(bash "$classify" "$tmp_log" | sed -n '1s/^kind=//p')" == "workflows-permission" ]]; then
  echo "OK   reads a log file argument"
else
  echo "::error::reading the log from a file argument did not classify correctly"
  failures=$((failures + 1))
fi
rm -f "$tmp_log"

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures of $total classify-push-failure case(s) did not behave as expected"
  exit 1
fi
echo "All $total classify-push-failure cases behaved as expected."
