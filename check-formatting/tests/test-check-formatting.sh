#!/usr/bin/env bash
#
# Offline tests for check-formatting YAML contracts.
#
# The `formatting` selftest job is the one that actually runs Air, against
# throwaway fixtures generated at runtime. This script cannot do that --
# it must not download Air, and it must not scan this repo's own `.R`
# files, which are not Air-formatted and must not be rewritten here
# (gha#333: land the capability; each consumer opts in with its own
# reformat commit).
#
# What it can pin is the half that fails silently when it drifts:
# action.yml and the reusable workflow declaring different defaults, or
# the setup-air pin's trailing comment naming the floating major tag
# (`# v1`) instead of the exact release (`# v1.0.1`), or the run line
# dropping `--check` or the end-of-options `--` before the path.
#
# Run with: bash check-formatting/tests/test-check-formatting.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
action_yml="$script_dir/../action.yml"
workflow_yml="$script_dir/../../.github/workflows/check-formatting.yml"

DEFAULT_VERSION='0.11.0'
DEFAULT_PATH='.'
SETUP_AIR_SHA='cf390573ff4fe0f198f35df3a642b1409328d859'
SETUP_AIR_RELEASE='v1.0.1'

failures=0
case_name=""

fail() {
  echo "  FAIL [$case_name]: $*" >&2
  failures=$((failures + 1))
}

yaml_default() {
  # Read the first `default:` for an input name without a YAML library --
  # the same line-scan approach check-new-line-breaks uses, because the
  # job that runs this installs nothing beyond bash.
  local file="$1"
  local input="$2"
  awk -v name="$input" '
    $0 ~ "^[[:space:]]*" name ":" { in_input = 1; next }
    in_input && $0 ~ /^[[:space:]]+description:/ { next }
    in_input && $0 ~ /^[[:space:]]+type:/ { next }
    in_input && $0 ~ /^[[:space:]]+default:/ {
      sub(/^[[:space:]]+default:[[:space:]]*/, "")
      gsub(/^'\''|'\''$/, "")
      print
      exit
    }
    in_input && $0 ~ /^[[:space:]]*[A-Za-z0-9_-]+:/ { in_input = 0 }
  ' "$file"
}

# --- The two declared defaults agree ----------------------------------------
# `version` and `path` are declared in action.yml and again in the reusable
# workflow. The gha#303 precedent applies -- assert the agreement rather
# than leaving it to a comment, since a drift here means a consumer of the
# reusable workflow gets a different pin from a consumer of the composite.
case_name="declared defaults agree"
for f in "$action_yml" "$workflow_yml"; do
  declared_version="$(yaml_default "$f" version)"
  if [ "$declared_version" != "$DEFAULT_VERSION" ]; then
    fail "$f declares version default '$declared_version', expected '$DEFAULT_VERSION'"
  fi
  declared_path="$(yaml_default "$f" path)"
  if [ "$declared_path" != "$DEFAULT_PATH" ]; then
    fail "$f declares path default '$declared_path', expected '$DEFAULT_PATH'"
  fi
done

# --- setup-air is SHA-pinned with the exact release in the comment ----------
# Upstream comments the same SHA `# v1`, a floating major tag. This repo's
# convention is the exact release (README "Pinning third-party actions").
# A comment of `# v1` would match the start of `# v1.0.1`, so require a
# dotted patch version after the SHA.
case_name="setup-air pin names the exact release"
uses_line="$(grep -E '^[[:space:]]*uses: posit-dev/setup-air@' "$action_yml" || true)"
if [ -z "$uses_line" ]; then
  fail "$action_yml has no posit-dev/setup-air uses: line"
else
  echo "$uses_line" | grep -Eq "posit-dev/setup-air@${SETUP_AIR_SHA} # ${SETUP_AIR_RELEASE}$" \
    || fail "expected 'uses: posit-dev/setup-air@${SETUP_AIR_SHA} # ${SETUP_AIR_RELEASE}', got: $uses_line"
  echo "$uses_line" | grep -Eq '# v[0-9]+\.[0-9]+\.[0-9]+$' \
    || fail "setup-air pin comment must be a dotted release, not a floating major tag: $uses_line"
fi

# --- The check is check-only ------------------------------------------------
# Dropping `--check` would make the composite rewrite files and exit 0.
# Dropping `--` would let a path that starts with `-` become an Air
# flag (`path: --force` bypasses include/exclude). The expected-failure
# e2e would catch the first, but an offline assertion is cheaper
# (gha#303: pin the contract that fails silently when reversed).
case_name="run line is check-only with end-of-options"
run_line="$(grep -E '^[[:space:]]*run: air format' "$action_yml" || true)"
if [ -z "$run_line" ]; then
  fail "$action_yml has no 'run: air format' line"
else
  echo "$run_line" | grep -Fq -- '--check' \
    || fail "expected air format invocation to carry --check, got: $run_line"
  echo "$run_line" | grep -Fq -- '-- "$AIR_PATH"' \
    || fail "expected end-of-options -- before the path, got: $run_line"
fi

if [ "$failures" -ne 0 ]; then
  echo "$failures assertion(s) failed." >&2
  exit 1
fi

echo "All check-formatting tests passed."
