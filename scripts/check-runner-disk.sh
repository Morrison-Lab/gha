#!/usr/bin/env bash
# Job-started hook for a self-hosted runner: fail the job at its start, with a
# clear message, when the disk is short, instead of letting a later step die
# with "No space left on device" (gha#1495).
#
# scripts/install-runner-cleanup-hook.sh points ACTIONS_RUNNER_HOOK_JOB_STARTED
# at this script. For each checked directory (CHECK_DISK_DIRS, default the
# temp folder /tmp and the runner's work folder), it needs CHECK_DISK_MIN_FREE_GB
# (default 5) free. The sweep covers temp folders only, so a short work folder
# on another filesystem is reported, not cleaned. When a directory is short, it first sweeps stale temp
# folders down to one hour old (scripts/sweep-runner-tmp.sh) and measures again.
# If it is still short it names the filesystem, the free space and the largest
# folders, and exits 1, which fails the job before it does any work.
#
# It also seeds the system Python into the runner's tool cache
# (scripts/seed-runner-python-toolcache.sh), so a runner whose work folder was
# moved or cleared after registration still has the entry actions/setup-python
# needs on Debian 13 (gha#1205). A seeding failure warns and never fails the job.
set -uo pipefail

# Run from a private copy (gha#1589). The runner executes this hook from the
# shared checkout, which sits on NFS and is fast-forwarded while jobs run; bash
# reads a script as it runs, so a replaced file fails mid-read with "Stale file
# handle". Copy this script and the ones it calls to a temp folder and run the
# copy. The if block is one compound command, so bash reads all of it before
# the exec; if copying fails, the hook runs in place as before.
if [ -z "${GHA_HOOK_STAGED:-}" ]; then
  src=$(dirname "${BASH_SOURCE[0]}")
  stage=$(mktemp -d) && cp "$src"/{check-runner-disk,prune-runner-workdir,sweep-runner-tmp,seed-runner-python-toolcache,wait-runner-capacity}.sh "$stage" &&
    GHA_HOOK_STAGED=$stage exec bash "$stage/$(basename "${BASH_SOURCE[0]}")" "$@"
  echo "::warning::$(basename "${BASH_SOURCE[0]}"): could not stage a private copy; running in place."
else
  trap 'rm -rf "$GHA_HOOK_STAGED"' EXIT
fi

# Seed the tool cache (RUNNER_TOOL_CACHE, else <work folder>/_tool from the checkout path).
tool_cache="${RUNNER_TOOL_CACHE:-${GITHUB_WORKSPACE:+$(dirname "$(dirname "$GITHUB_WORKSPACE")")/_tool}}"
if [ -n "$tool_cache" ]; then
  RUNNER_TOOL_CACHE="$tool_cache" RUNNER_DIR="$tool_cache" \
    bash "$(dirname "${BASH_SOURCE[0]}")/seed-runner-python-toolcache.sh" > /dev/null ||
    echo "::warning::check-runner-disk: Python toolcache seeding failed; Python-based checks may fail."
fi

min_free_gb="${CHECK_DISK_MIN_FREE_GB:-5}"
case "$min_free_gb" in
  '' | *[!0-9]*) echo "::warning::check-runner-disk: CHECK_DISK_MIN_FREE_GB must be a whole number; not checked."; exit 0 ;;
esac
read -r -a dirs <<< "${CHECK_DISK_DIRS:-/tmp ${GITHUB_WORKSPACE:+$(dirname "$(dirname "$GITHUB_WORKSPACE")")}}"

free_gb() { df -Pk "$1" 2> /dev/null | awk 'NR == 2 { print int($4 / 1048576) }'; }

failed=0
swept=0
for d in "${dirs[@]}"; do
  [ -d "$d" ] || continue
  free=$(free_gb "$d")
  [ -n "$free" ] || continue
  if [ "$free" -lt "$min_free_gb" ] && [ "$swept" = 0 ]; then
    SWEEP_TMP_MAX_AGE_HOURS=1 bash "$(dirname "${BASH_SOURCE[0]}")/sweep-runner-tmp.sh"
    swept=1
    free=$(free_gb "$d")
  fi
  if [ "$free" -lt "$min_free_gb" ]; then
    mount=$(df -Pk "$d" | awk 'NR == 2 { print $1 " mounted on " $6 }')
    # df follows a symlinked folder, so name where the link points (gha#1585).
    real=$(realpath "$d" 2> /dev/null)
    shown="$d"
    if [ -n "$real" ] && [ "$real" != "$d" ]; then shown="$d (a link to $real)"; fi
    echo "::error::check-runner-disk: $shown has $free GB free on $mount, under the $min_free_gb GB needed. Largest folders:"
    du -xk --max-depth=1 "$d" 2> /dev/null | sort -rn | head -n 6 |
      awk '{ printf "  %.1f GB  %s\n", $1 / 1048576, $2 }'
    failed=1
  fi
done
if [ "$failed" = 0 ]; then
  # Hold the job until the host has memory and CPU to spare (gha#1509).
  bash "$(dirname "${BASH_SOURCE[0]}")/wait-runner-capacity.sh"
fi
exit "$failed"
