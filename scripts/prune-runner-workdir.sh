#!/usr/bin/env bash
# Job-completed hook for a self-hosted runner: delete repository checkouts in
# the runner's work folder that no job has used for a while, and more of them
# when the disk is short (gha#1352).
#
# The runner keeps every repository it has ever checked out under
# <work folder>/<repo>/, and never removes one. On cf463-01 three runners
# filled a 28 GB /var in six days (2026-10-23 to 10-29), and jobs then failed
# with "No space left on device" (Morrison-Lab/mcsg#54).
#
# scripts/install-runner-cleanup-hook.sh points ACTIONS_RUNNER_HOOK_JOB_COMPLETED
# at this script, so the runner runs it after every job, with GITHUB_WORKSPACE
# set to that job's checkout (<work folder>/<repo>/<repo>).
#
# Two passes over the checkouts other than the current job's, oldest first:
#   1. delete any not used for PRUNE_MAX_AGE_DAYS (default 7, at least 1);
#   2. while the work folder's filesystem has less than PRUNE_MIN_FREE_GB
#      (default 10) free, delete the oldest remaining one.
# Directories whose name starts with `_` (_tool, _actions, _temp, ...) are the
# runner's own and are never touched.
#
# A failure here warns and exits 0 rather than failing: the job has already
# finished, and a red job over housekeeping would hide whether the job itself
# passed. The runner runs a .sh hook as `bash -e -o pipefail`, so errexit is
# turned off explicitly and every command's failure is handled where it runs.
set +e
set -uo pipefail

warn() { echo "::warning::prune-runner-workdir: $*"; }

max_age_days="${PRUNE_MAX_AGE_DAYS:-7}"
min_free_gb="${PRUNE_MIN_FREE_GB:-10}"
case "$max_age_days$min_free_gb" in
  *[!0-9]*) warn "PRUNE_MAX_AGE_DAYS and PRUNE_MIN_FREE_GB must be whole numbers; nothing pruned."; exit 0 ;;
esac
if [ -z "$max_age_days" ] || [ -z "$min_free_gb" ] || [ "$max_age_days" -lt 1 ]; then
  warn "PRUNE_MAX_AGE_DAYS must be at least 1 and PRUNE_MIN_FREE_GB set; nothing pruned."
  exit 0
fi

workspace="${GITHUB_WORKSPACE:-}"
case "$workspace" in
  /*/*/*) ;;
  *) warn "GITHUB_WORKSPACE is not an absolute <work>/<repo>/<repo> path ('$workspace'); nothing pruned."; exit 0 ;;
esac
current=$(dirname "$workspace")
work=$(dirname "$current")
if [ ! -d "$work" ] || [ "$work" = / ]; then
  warn "work folder '$work' is not a directory; nothing pruned."
  exit 0
fi

# A checkout's own mtime does not change when a later job reuses it, so the
# hook marks the one this job used; age then means time since the last job.
if ! touch "$current"; then
  warn "could not mark $current as used; nothing pruned."
  exit 0
fi

# Prints the free kilobytes on the work folder's filesystem, or nothing.
free_kb() {
  local kb
  kb=$(df -Pk "$work" 2> /dev/null | awk 'NR == 2 { print $4 }') || kb=''
  case "$kb" in '' | *[!0-9]*) kb='' ;; esac
  printf '%s' "$kb"
}

remove() {
  if rm -rf -- "$1"; then
    echo "prune-runner-workdir: removed $1 ($2)"
  else
    warn "could not remove $1"
  fi
}

# The checkouts other than the current job's, oldest use first, NUL-separated.
candidates() {
  find "$work" -mindepth 1 -maxdepth 1 -type d ! -name '_*' -printf '%T@ %p\0' |
    LC_ALL=C sort -z -n | while IFS= read -r -d '' line; do
      d="${line#* }"
      [ "$d" = "$current" ] || printf '%s\0' "$d"
    done
}

# Pass 1: -mtime +N matches at least N + 1 whole days, so N = days - 1.
while IFS= read -r -d '' d; do
  [ "$d" = "$current" ] && continue
  remove "$d" "unused for over $max_age_days days"
done < <(find "$work" -mindepth 1 -maxdepth 1 -type d ! -name '_*' \
  -mtime "+$((max_age_days - 1))" -print0)

# Pass 2.
min_free_kb=$((min_free_gb * 1024 * 1024))
pruned_all=1
while IFS= read -r -d '' d; do
  free=$(free_kb)
  if [ -z "$free" ]; then
    warn "could not read free space for $work; stopped pruning."
    exit 0
  fi
  if [ "$free" -ge "$min_free_kb" ]; then
    pruned_all=0
    break
  fi
  remove "$d" "under ${min_free_gb} GB free"
done < <(candidates)

free=$(free_kb)
if [ -n "$free" ] && [ "$free" -lt "$min_free_kb" ] && [ "$pruned_all" = 1 ]; then
  warn "$work still has under ${min_free_gb} GB free after removing every other checkout; the next jobs will re-clone them."
fi
exit 0
