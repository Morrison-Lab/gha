#!/usr/bin/env bash
# Job-started hook for a self-hosted runner: fail the job at its start, with a
# clear message, when the disk is short, instead of letting a later step die
# with "No space left on device" (gha#1495).
#
# scripts/install-runner-cleanup-hook.sh points ACTIONS_RUNNER_HOOK_JOB_STARTED
# at this script. For each checked directory (CHECK_DISK_DIRS, default the
# temp folder /tmp and the runner's work folder), it needs CHECK_DISK_MIN_FREE_GB
# (default 5) free. When a directory is short, it first sweeps stale temp
# folders down to one hour old (scripts/sweep-runner-tmp.sh) and measures again.
# If it is still short it names the filesystem, the free space and the largest
# folders, and exits 1, which fails the job before it does any work.
set -uo pipefail

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
    echo "::error::check-runner-disk: $d has $free GB free on $mount, under the $min_free_gb GB needed. Largest folders:"
    du -xk --max-depth=1 "$d" 2> /dev/null | sort -rn | head -n 6 |
      awk '{ printf "  %.1f GB  %s\n", $1 / 1048576, $2 }'
    failed=1
  fi
done
exit "$failed"
