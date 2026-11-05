#!/usr/bin/env bash
# Run one check inside a bundled job (lds#1839), so many small checks can share
# ONE HTCondor job (WWU CS IT: submit batch jobs, not many small ones).
#
# Usage: run-check.sh <name> [VAR=value ...] -- <command> [args...]
#
# The wrapper
#   - runs the command with the VAR=value pairs added to its environment
#     (the same variables a check's action.yml sets from its inputs);
#   - prints the output between ::group::<name> and ::endgroup::;
#   - adds title=<name> to every ::warning, ::error and ::notice line that has
#     none, so the annotation gate and a reader can tell which check wrote it;
#   - appends one row to a Markdown table at $RUN_CHECK_SUMMARY (default
#     $GITHUB_STEP_SUMMARY; standard output when neither is set);
#   - exits with the command's exit code, so a step that follows can go on and
#     the bundle's last failing code is reported, as condor-batch does.
#
# <name> is the check's workflow job name, such as check-avoided-words; it may
# hold only letters, digits, '.', '_' and '-'.
set -uo pipefail

name="${1:-}"
if [ -z "$name" ] || ! [[ "$name" =~ ^[A-Za-z0-9._-]+$ ]]; then
  echo "usage: run-check.sh <name> [VAR=value ...] -- <command> [args...]" >&2
  exit 64
fi
shift
envs=()
while [ $# -gt 0 ] && [ "$1" != "--" ]; do
  case "$1" in
    [A-Za-z_]*=*) envs+=("$1"); shift ;;
    *) echo "run-check: expected VAR=value or --, got: $1" >&2; exit 64 ;;
  esac
done
[ "${1:-}" = "--" ] && shift
if [ $# -eq 0 ]; then
  echo "run-check: no command given" >&2
  exit 64
fi

# Skip a workflow command that already has a title; otherwise add one, with a
# comma when the command already has properties.
sed_script='/^::(warning|error|notice)[ :]/{
  /^::[a-z]+ [^:]*title=/b
  s/^::(warning|error|notice)::/::\1 title=@NAME@::/
  t
  s/^::(warning|error|notice) ([^:]*)::/::\1 title=@NAME@,\2::/
}'
sed_script="${sed_script//@NAME@/$name}"

echo "::group::$name"
env ${envs[@]+"${envs[@]}"} "$@" 2>&1 | sed -E -e "$sed_script"
rc=${PIPESTATUS[0]}
echo "::endgroup::"

if [ "$rc" -eq 0 ]; then status="pass"; else status="FAIL"; fi
summary="${RUN_CHECK_SUMMARY:-${GITHUB_STEP_SUMMARY:-}}"
row="| $name | $status | $rc |"
if [ -n "$summary" ]; then
  if [ ! -s "$summary" ]; then
    printf '| Check | Result | Exit code |\n| --- | --- | --- |\n' >> "$summary"
  fi
  printf '%s\n' "$row" >> "$summary"
else
  echo "$row"
fi
exit "$rc"
