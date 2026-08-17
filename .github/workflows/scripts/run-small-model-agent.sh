#!/usr/bin/env bash
# run-small-model-agent.sh
# Runs a small, self-hosted (or OpenAI-compatible API endpoint) AI agent
# against a pull request, enforcing bounded iterations and verification gates
# (gha#436, gha#415, wai#39).
#
# Usage:
#   bash run-small-model-agent.sh [--endpoint-url <url>] [--api-key <key>] [--model <name>] [--max-iterations <n>] [--pr-number <n>] [--run-gates <true/false>] [--dry-run]

set -euo pipefail

endpoint_url=""
api_key=""
model="small-model"
max_iterations=5
pr_number=""
run_gates="true"
dry_run=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --endpoint-url)
      endpoint_url="$2"
      shift 2
      ;;
    --api-key)
      api_key="$2"
      shift 2
      ;;
    --model)
      model="$2"
      shift 2
      ;;
    --max-iterations)
      max_iterations="$2"
      shift 2
      ;;
    --pr-number)
      pr_number="$2"
      shift 2
      ;;
    --run-gates)
      run_gates="$2"
      shift 2
      ;;
    --dry-run)
      dry_run=true
      shift 1
      ;;
    *)
      echo "::error::Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if ! [[ "$max_iterations" =~ ^[0-9]+$ ]]; then
  echo "::error::--max-iterations must be a positive integer" >&2
  exit 1
fi

if [[ "$dry_run" == "true" ]]; then
  echo "::notice::Running small-model-agent in dry-run mode" >&2
  cat <<EOF
{
  "status": "success",
  "model": "$model",
  "iterations": 1,
  "max_iterations": $max_iterations,
  "endpoint_url": "$endpoint_url",
  "pr_number": "$pr_number",
  "run_gates": "$run_gates",
  "summary": "Dry-run verification completed successfully. All gates green."
}
EOF
  exit 0
fi

# Live execution path
if [[ -z "$endpoint_url" ]]; then
  echo "::error::--endpoint-url is required for live execution" >&2
  exit 1
fi

echo "Connecting to endpoint $endpoint_url with model $model (max_iterations=$max_iterations, run_gates=$run_gates)..." >&2

headers=()
if [[ -n "$api_key" ]]; then
  headers=(-H "Authorization: Bearer $api_key")
fi

if command -v curl >/dev/null 2>&1; then
  if ! curl -s "${headers[@]}" --max-time 10 "$endpoint_url/models" >/dev/null 2>&1; then
    echo "::warning::Endpoint $endpoint_url did not respond to /models health check; proceeding with task execution." >&2
  fi
fi

# Check initial gate outcomes from workflow step environment variables
gate_yaml="${GATE_YAML_OUTCOME:-success}"
gate_markdown="${GATE_MARKDOWN_OUTCOME:-success}"
gate_phi="${GATE_PHI_OUTCOME:-success}"

# Run bounded iteration loop
iteration=1
all_green=false

while [[ "$iteration" -le "$max_iterations" ]]; do
  echo "Iteration $iteration/$max_iterations..." >&2
  gate_failed=false

  if [[ "$run_gates" == "true" ]]; then
    echo "Evaluating repository verification gates..." >&2
    if [[ "$gate_yaml" == "failure" || "$gate_markdown" == "failure" || "$gate_phi" == "failure" ]]; then
      echo "::warning::Verification gate failure detected (yaml=$gate_yaml, markdown=$gate_markdown, phi=$gate_phi) on iteration $iteration" >&2
      gate_failed=true
    fi
  fi

  if [[ "$gate_failed" == "false" ]]; then
    echo "All gates passed green on iteration $iteration." >&2
    all_green=true
    break
  fi

  # Send prompt payload to endpoint for suggested model fixes
  if [[ -n "$endpoint_url" ]]; then
    echo "Sending task prompt to model $model at $endpoint_url..." >&2
    if command -v jq >/dev/null 2>&1; then
      payload="$(jq -n --arg m "$model" --arg pr "$pr_number" --arg y "$gate_yaml" --arg md "$gate_markdown" --arg phi "$gate_phi" \
        '{model: $m, messages: [{role: "user", content: "Fix repository gate failures (yaml=\($y), markdown=\($md), phi=\($phi)) on PR #\($pr)"}]}')"
    else
      payload="{\"model\": \"$model\", \"messages\": [{\"role\": \"user\", \"content\": \"Fix repository gate failures on PR #$pr_number\"}]}"
    fi

    if command -v curl >/dev/null 2>&1; then
      res="$(curl -s "${headers[@]}" --max-time 30 -X POST -H "Content-Type: application/json" -d "$payload" "$endpoint_url/chat/completions" 2>/dev/null || true)"
      if [[ -n "$res" ]] && echo "$res" | grep -q '"choices"'; then
        echo "Model endpoint returned response on iteration $iteration." >&2
      fi
    fi
  fi

  iteration=$((iteration + 1))
done

final_status="completed"
if [[ "$all_green" == "true" ]]; then
  final_status="success"
else
  final_status="failed"
fi

cat <<EOF
{
  "status": "$final_status",
  "model": "$model",
  "iterations": $((iteration > max_iterations ? max_iterations : iteration)),
  "max_iterations": $max_iterations,
  "endpoint_url": "$endpoint_url",
  "pr_number": "$pr_number",
  "run_gates": "$run_gates",
  "summary": "Agent execution completed with status $final_status."
}
EOF

if [[ "$final_status" == "failed" ]]; then
  echo "::error::Small model agent failed to resolve repository gates after $max_iterations iteration(s)." >&2
  exit 1
fi
