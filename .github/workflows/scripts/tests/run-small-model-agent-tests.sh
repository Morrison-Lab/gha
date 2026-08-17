#!/usr/bin/env bash
# Exercises run-small-model-agent.sh offline (gha#436, gha#415).
# Usage: bash .github/workflows/scripts/tests/run-small-model-agent-tests.sh

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"
agent_script="$repo_root/.github/workflows/scripts/run-small-model-agent.sh"

failures=0

# Test 1: Dry run mode output contains expected status
out="$(bash "$agent_script" --dry-run --model "test-model" --max-iterations 3 --pr-number "123")"
if echo "$out" | grep -q '"status": "success"' && echo "$out" | grep -q '"model": "test-model"'; then
  echo "OK   run-small-model-agent.sh --dry-run returned expected JSON"
else
  echo "::error::run-small-model-agent.sh --dry-run failed to return expected JSON; got: $out"
  failures=$((failures + 1))
fi

# Test 2: Missing --endpoint-url in live mode exits non-zero
if bash "$agent_script" --model "test-model" >/dev/null 2>&1; then
  echo "::error::run-small-model-agent.sh should fail when --endpoint-url is missing in live mode"
  failures=$((failures + 1))
else
  echo "OK   run-small-model-agent.sh fails when --endpoint-url missing in live mode"
fi

# Test 3: Live mode execution with gate failure reports status=failed and exits non-zero
out=""
if out="$(GATE_YAML_OUTCOME="failure" bash "$agent_script" --endpoint-url "http://localhost:9999/v1" --model "test-model" --max-iterations 2 --pr-number "123" 2>&1)"; then
  echo "::error::run-small-model-agent.sh should exit non-zero when gates remain failed"
  failures=$((failures + 1))
else
  if echo "$out" | grep -q '"status": "failed"'; then
    echo "OK   run-small-model-agent.sh reports status=failed and exits non-zero when gates fail"
  else
    echo "::error::run-small-model-agent.sh failed to report status=failed; got: $out"
    failures=$((failures + 1))
  fi
fi

# Test 4: Live mode execution with green gates reports status=success and exits zero
out="$(GATE_YAML_OUTCOME="success" GATE_MARKDOWN_OUTCOME="success" bash "$agent_script" --endpoint-url "http://localhost:9999/v1" --model "test-model" --max-iterations 2 --pr-number "123")"
if echo "$out" | grep -q '"status": "success"'; then
  echo "OK   run-small-model-agent.sh reports status=success when all gates pass"
else
  echo "::error::run-small-model-agent.sh failed to report status=success when all gates pass; got: $out"
  failures=$((failures + 1))
fi

if [[ "$failures" -gt 0 ]]; then
  echo "::error::$failures run-small-model-agent test case(s) failed"
  exit 1
fi

echo "All run-small-model-agent test cases passed."
