#!/usr/bin/env bash
# Offline tests for the two workflow audits `_selftest.yml` runs (gha#716).
#
# These cover the AUDITS, not just the discovery helper underneath them. That
# distinction is the point: this repo's real tree carries 63 `.yml` workflows
# and zero `.yaml` ones, so a consumer reverted to a `*.yml`-only glob would
# leave every other check green. Each audit therefore gets a fixture whose
# violation lives in a `.yaml` file, which no yml-only discovery can see.
#
# Usage: bash .github/workflows/scripts/tests/run-workflow-audit-tests.sh
set -uo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TOKEN_AUDIT="$script_dir/../audit-workflow-token-usage.sh"
PINS_AUDIT="$script_dir/../audit-workflow-action-pins.sh"

for s in "$TOKEN_AUDIT" "$PINS_AUDIT"; do
  if [ ! -f "$s" ]; then
    echo "::error::audit script not found at $s" >&2
    exit 1
  fi
done

failures=0
cases=0

# expect <label> <script> <dir> <want-rc> [needle]
expect() {
  local label="$1" script="$2" dir="$3" want_rc="$4" needle="${5:-}"
  cases=$((cases + 1))
  local out rc
  out="$(bash "$script" "$dir" 2>&1)"
  rc=$?
  if [ "$rc" -ne "$want_rc" ]; then
    echo "::error::$label: expected exit $want_rc, got $rc; output: $out" >&2
    failures=$((failures + 1))
    return
  fi
  if [ -n "$needle" ] && ! printf '%s' "$out" | grep -qF "$needle"; then
    echo "::error::$label: expected output to mention '$needle'; output: $out" >&2
    failures=$((failures + 1))
    return
  fi
  echo "OK   $label"
}

tmp="$(mktemp -d)"
trap 'chmod -R u+rwX "$tmp" 2>/dev/null; rm -rf "$tmp"' EXIT

# The literal that must not appear in a workflow, assembled rather than typed
# so this fixture text cannot be mistaken for a real violation by a future
# audit run over this repo's own tree.
# shellcheck disable=SC2016  # the literal must NOT expand; it is fixture text.
EXPR_OPEN='${{'
BAD_TOKEN="      token: ${EXPR_OPEN} secrets.SUBMODULES_TOKEN }}"
OK_TOKEN="      submodules-token: ${EXPR_OPEN} secrets.SUBMODULES_TOKEN }}"

mk() { mkdir -p "$(dirname "$1")"; printf '%s\n' "$2" > "$1"; }

# ---------------------------------------------------------------- token audit
clean="$tmp/token-clean"
mk "$clean/a.yml" "jobs:
  run:
    steps:
      - uses: actions/checkout@1111111111111111111111111111111111111111
$OK_TOKEN"
expect "token: a clean tree passes" "$TOKEN_AUDIT" "$clean" 0 "No workflow passes"
expect "token: submodules-token: is not flagged" "$TOKEN_AUDIT" "$clean" 0

yml_bad="$tmp/token-bad-yml"
mk "$yml_bad/a.yml" "jobs:
  run:
    steps:
      - uses: actions/checkout@1111111111111111111111111111111111111111
$BAD_TOKEN"
expect "token: a .yml violation fails" "$TOKEN_AUDIT" "$yml_bad" 1 "gha#442"

# The discovery-revert detector: identical fixture, .yaml extension.
yaml_bad="$tmp/token-bad-yaml"
mk "$yaml_bad/a.yaml" "jobs:
  run:
    steps:
      - uses: actions/checkout@1111111111111111111111111111111111111111
$BAD_TOKEN"
expect "token: a .yaml violation fails too" "$TOKEN_AUDIT" "$yaml_bad" 1 "gha#442"

expect "token: an empty directory fails closed" "$TOKEN_AUDIT" "$tmp/token-empty-missing" 1 "workflows directory not found"

# ----------------------------------------------------------------- pins audit
# Every fixture below writes the CONTINUATION form (`uses:` on its own line),
# because that is the only form the audit anchors on --- see the blind-spot
# case at the end of this section, and gha#720.
pins_clean="$tmp/pins-clean"
mk "$pins_clean/a.yml" "jobs:
  run:
    steps:
      - name: pinned
        uses: actions/checkout@1111111111111111111111111111111111111111
      - name: local
        uses: ./.github/actions/local-thing
      - name: self
        uses: Morrison-Lab/gha/.github/workflows/spellcheck.yml@v2"
expect "pins: pinned, local and self refs pass" "$PINS_AUDIT" "$pins_clean" 0 "are SHA-pinned"

pins_bad_yml="$tmp/pins-bad-yml"
mk "$pins_bad_yml/a.yml" "jobs:
  run:
    steps:
      - name: unpinned
        uses: actions/checkout@v4"
expect "pins: an unpinned .yml ref fails" "$PINS_AUDIT" "$pins_bad_yml" 1 "gha#328"

# The discovery-revert detector for this audit: identical fixture, .yaml
# extension. A `*.yml`-only glob turns this red and nothing else in the repo
# would, since the real tree carries no .yaml workflows.
pins_bad_yaml="$tmp/pins-bad-yaml"
mk "$pins_bad_yaml/a.yaml" "jobs:
  run:
    steps:
      - name: unpinned
        uses: actions/checkout@v4"
expect "pins: an unpinned .yaml ref fails too" "$PINS_AUDIT" "$pins_bad_yaml" 1 "gha#328"

# gha#720, pinned as CURRENT behaviour rather than as desired behaviour: the
# list-item form is invisible to this audit. Asserting it keeps the gap from
# being rediscovered as a mystery, and makes the eventual fix turn this case
# red, which is the prompt to update it rather than a regression.
pins_list_form="$tmp/pins-list-form"
mk "$pins_list_form/a.yml" "jobs:
  run:
    steps:
      - uses: actions/checkout@v4"
expect "pins: the '- uses:' list form is NOT yet examined (gha#720)" \
  "$PINS_AUDIT" "$pins_list_form" 0 "are SHA-pinned"

pins_no_uses="$tmp/pins-no-uses"
mk "$pins_no_uses/a.yml" "jobs:
  run:
    steps:
      - run: 'true'"
expect "pins: a workflow set with no uses: passes" "$PINS_AUDIT" "$pins_no_uses" 0 "are SHA-pinned"

# ------------------------------------------------- grep's third exit status
# An unreadable file makes grep exit 2. Both audits must report that the check
# did not run rather than folding it into "clean" --- the defect the old inline
# `if grep ...; then` and `|| true` forms each had. Skipped as root, where the
# permission bit does not bite.
if [ "$(id -u)" -eq 0 ]; then
  echo "SKIP running as root: unreadable-file cases cannot be exercised"
else
  for pair in "token:$TOKEN_AUDIT" "pins:$PINS_AUDIT"; do
    name="${pair%%:*}"
    audit="${pair#*:}"
    unreadable="$tmp/unreadable-$name"
    mk "$unreadable/a.yml" "jobs: {}"
    chmod 000 "$unreadable/a.yml"
    expect "$name: an unreadable workflow is an audit failure, not a pass" \
      "$audit" "$unreadable" 2 "did not run to completion"
    chmod u+rw "$unreadable/a.yml"
  done
fi

if [ "$failures" -ne 0 ]; then
  echo "::error::$failures of $cases workflow-audit test case(s) failed" >&2
  exit 1
fi
echo "All $cases workflow-audit tests passed."
