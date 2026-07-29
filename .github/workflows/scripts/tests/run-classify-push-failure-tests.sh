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
#
# Note what is NOT here: a `GH013` line. An earlier revision of this fixture
# carried one, and a review round then reasoned from it that GitHub wraps a
# workflow-permission rejection in the generic rule-violation envelope. It
# does not -- the line was invented here, and the claim was published on the
# PR before anyone checked it against the issue. Keep this fixture verbatim;
# the co-occurrence case below is where both markers belong.
app_rejection=$(cat <<'EOF'
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

# GitHub's secret-scanning push protection. This one must NOT fall through to
# `other`: `other` publishes the patch, and here the commits are exactly what
# must not be republished (gha#361 review).
push_protection=$(cat <<'EOF'
remote: error: GH013: Repository rule violations found for refs/heads/topic.
remote:
remote: - GITHUB PUSH PROTECTION
remote:   Resolve the following secrets before pushing again.
remote:      - Anthropic API Key
remote:        locations:
remote:          - commit: 1234567
remote:            path: config.yml:3
EOF
)

# The wording GitHub uses when the rule violation is reported without the
# GH013 code, e.g. in some rule-set configurations.
push_protection_alt='remote: error: push declined due to repository rule violations'

# The case that motivated splitting `withhold-patch` out of `kind`: one push
# that both edits a workflow file AND carries a secret, so BOTH clauses match.
# `kind` is a first-match chain, so workflows-permission wins and the reader
# gets that explanation -- but the commits still hold the credential, so the
# patch must be withheld anyway. A gate keyed on `kind` published it (gha#361
# review round 5).
both_markers=$(cat <<'EOF'
remote: error: GH013: Repository rule violations found for refs/heads/topic.
remote: - GITHUB PUSH PROTECTION
remote:   Resolve the following secrets before pushing again.
remote:      - Anthropic API Key
 ! [remote rejected] HEAD -> topic (refusing to allow a GitHub App to create or update workflow `.github/workflows/validate.yml` without `workflows` permission)
EOF
)

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

# check_withhold <name> <log> <expected true|false>
#
# The security-relevant output, and the one that must be asserted separately
# from `kind`: the composite gates publication of the patch on this line, not
# on the kind.
check_withhold() {
  local name="$1" log="$2" want="$3" got
  total=$((total + 1))
  got="$(printf '%s\n' "$log" | bash "$classify" - | sed -n '2s/^withhold-patch=//p')"
  if [[ "$got" == "$want" ]]; then
    echo "OK   $name"
  else
    echo "::error::$name: expected withhold-patch '$want' but got '$got'"
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
check_kind "push protection (GH013)"        "$push_protection"     push-protection
check_kind "push protection (rule wording)" "$push_protection_alt" push-protection
# Both clauses match. The chain is first-match, so the reader gets the more
# specific workflows-permission explanation...
check_kind "co-occurring markers pick the specific kind" "$both_markers" workflows-permission

# ... but the patch is withheld regardless, because the commits still carry
# whatever secret scanning caught. This pair is the whole reason the two
# outputs are computed independently -- a gate keyed on `kind` publishes it.
check_withhold "co-occurring markers still withhold"  "$both_markers"    true
check_withhold "push protection withholds"            "$push_protection" true
check_withhold "plain workflows rejection publishes"  "$app_rejection"   false
check_withhold "unrecognized failure publishes"       "$auth_failure"    false

# The advice must say the patch is withheld -- the suppression itself is keyed
# on `withhold-patch`, but the reader learns of it only from this text.
check_advice "push protection says no patch" "$push_protection" "No patch is included" has
# ... including when another kind won the chain and supplied the advice, which
# is the case where the omission would otherwise be silent.
check_advice "co-occurring case explains the missing patch" "$both_markers" "No patch is included" has
# A secret-bearing rejection must never be classified as anything that would
# publish the commits; this is the assertion guarding that.
check_advice "push protection names rotation" "$push_protection" "rotate" has

# The whole point of the workflows-permission branch is naming the secret that
# is missing; a generic failure must NOT name it, or the advice sends a reader
# to configure something unrelated to what actually broke.
check_advice "names WORKFLOW_TOKEN"          "$app_rejection" "WORKFLOW_TOKEN"          has
check_advice "links the README permissions"  "$app_rejection" "gha#permissions"         has
check_advice "generic case omits the secret" "$auth_failure"  "WORKFLOW_TOKEN"          lacks

# The output contract the composite action parses, by line: `kind=`,
# `withhold-patch=`, `headline=`, a blank, then advice. The composite reads
# each by fixed offset, so a reordering here breaks it silently.
total=$((total + 1))
out="$(printf '%s\n' "$app_rejection" | bash "$classify" -)"
if [[ "$(sed -n '1p' <<<"$out")" == kind=* ]] &&
   [[ "$(sed -n '2p' <<<"$out")" == withhold-patch=* ]] &&
   [[ "$(sed -n '3p' <<<"$out")" == headline=* ]] &&
   [[ -z "$(sed -n '4p' <<<"$out")" ]] &&
   [[ -n "$(tail -n +5 <<<"$out")" ]]; then
  echo "OK   output shape (kind / withhold-patch / headline / blank / advice)"
else
  echo "::error::output shape: expected kind, withhold-patch, headline, blank line, then advice"
  failures=$((failures + 1))
fi

# The headline reaches an `::error::` annotation, which is a single line.
total=$((total + 1))
if [[ "$(sed -n '3s/^headline=//p' <<<"$out" | wc -l)" -eq 1 ]]; then
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
