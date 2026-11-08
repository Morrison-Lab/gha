#!/usr/bin/env bash
# Remove stale git lock files that a killed or cancelled job left in a runner's
# checkouts (gha#1661). On cf463-01 a job left <checkout>/.git/modules/rme/index.lock,
# and the next job on the same runner failed in `git submodule update` with
# "Unable to create ... index.lock: File exists".
#
# Called by scripts/prune-runner-workdir.sh after each job, with the runner's
# work folder as the only argument (or SWEEP_LOCK_WORK).
#
# A lock file is removed only when all of these hold:
#   - it is a regular file named *.lock directly under <work>/<repo>/<repo>/.git
#     or anywhere under <work>/<repo>/<repo>/.git/modules;
#   - the current user owns it;
#   - it has not changed for SWEEP_LOCK_MIN_AGE_MINUTES (default 10, at least 1),
#     so a lock a running git just took is kept;
#   - no git process has a working directory inside the work folder, so a git
#     command that still holds a lock is never undercut.
# Nothing else is touched. A failure warns and exits 0, because housekeeping
# must not turn a finished job red.
set +e
set -uo pipefail

warn() { echo "::warning::sweep-runner-git-locks: $*"; }

work="${1:-${SWEEP_LOCK_WORK:-}}"
min_age="${SWEEP_LOCK_MIN_AGE_MINUTES:-10}"
case "$min_age" in
  '' | *[!0-9]*) warn "SWEEP_LOCK_MIN_AGE_MINUTES must be a whole number; nothing swept."; exit 0 ;;
esac
if [ "$min_age" -lt 1 ]; then
  warn "SWEEP_LOCK_MIN_AGE_MINUTES must be at least 1; nothing swept."
  exit 0
fi
if [ -z "$work" ] || [ ! -d "$work" ]; then
  warn "work folder '$work' is not a directory; nothing swept."
  exit 0
fi

# True when a git process of this user runs with a working directory in $work.
git_running_in_work() {
  local pid cwd
  for pid in $(pgrep -u "$(id -u)" -x git 2> /dev/null); do
    cwd=$(readlink "/proc/$pid/cwd" 2> /dev/null)
    case "$cwd" in "$work"/*) return 0 ;; esac
  done
  return 1
}

if git_running_in_work; then
  echo "sweep-runner-git-locks: a git process is running in $work; nothing swept."
  exit 0
fi

me=$(id -un)
removed=0
for repo in "$work"/*/; do
  name=$(basename "$repo")
  case "$name" in _*) continue ;; esac
  gitdir="$repo$name/.git"
  [ -d "$gitdir" ] || continue
  while IFS= read -r -d '' lock; do
    if rm -f -- "$lock"; then
      removed=$((removed + 1))
      echo "sweep-runner-git-locks: removed $lock (unchanged for over $min_age minutes)"
    else
      warn "could not remove $lock"
    fi
  done < <({
    find "$gitdir" -maxdepth 1 -type f -name '*.lock' -user "$me" -mmin "+$min_age" -print0
    [ -d "$gitdir/modules" ] &&
      find "$gitdir/modules" -type f -name '*.lock' -user "$me" -mmin "+$min_age" -print0
  })
done
echo "sweep-runner-git-locks: removed $removed lock file(s)"
exit 0
