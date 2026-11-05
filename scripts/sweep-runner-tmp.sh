#!/usr/bin/env bash
# Remove stale temp folders that jobs on a self-hosted runner left behind
# (gha#1495): R's Rtmp*, Quarto's quarto-session*, and the other folders named
# in SWEEP_TMP_PATTERNS. On cf463-01 a killed or cancelled job left about 65 GB
# of them in /tmp.
#
# Called by scripts/prune-runner-workdir.sh after each job, and by the
# gha-runner-tmp-sweep.timer user unit once a day, so a host whose runners are
# idle or offline is still swept.
#
# A folder is removed only when all of these hold:
#   - it sits directly in a swept directory (SWEEP_TMP_DIRS, default $TMPDIR or /tmp);
#   - its name matches a pattern in SWEEP_TMP_PATTERNS (default "Rtmp* quarto-session*");
#   - the current user owns it, so nothing needs sudo and no one else's files are touched;
#   - neither it nor anything inside it changed in the last SWEEP_TMP_MAX_AGE_HOURS
#     (default 24, at least 1), so a folder a running job still writes to is kept.
# Nothing else in the directory is touched. Failures warn and exit 0, because
# housekeeping must not turn a finished job red.
set +e
set -uo pipefail

warn() { echo "::warning::sweep-runner-tmp: $*"; }

max_age_hours="${SWEEP_TMP_MAX_AGE_HOURS:-24}"
case "$max_age_hours" in
  '' | *[!0-9]*) warn "SWEEP_TMP_MAX_AGE_HOURS must be a whole number; nothing swept."; exit 0 ;;
esac
if [ "$max_age_hours" -lt 1 ]; then
  warn "SWEEP_TMP_MAX_AGE_HOURS must be at least 1; nothing swept."
  exit 0
fi
read -r -a patterns <<< "${SWEEP_TMP_PATTERNS:-Rtmp* quarto-session*}"
read -r -a dirs <<< "${SWEEP_TMP_DIRS:-${TMPDIR:-/tmp}}"
me=$(id -un)
removed_kb=0

for dir in "${dirs[@]}"; do
  [ -d "$dir" ] || continue
  name_args=()
  for p in "${patterns[@]}"; do
    [ "${#name_args[@]}" -gt 0 ] && name_args+=(-o)
    name_args+=(-name "$p")
  done
  [ "${#name_args[@]}" -gt 0 ] || continue
  while IFS= read -r -d '' d; do
    # Keep the folder if anything in it changed within the window.
    if [ -n "$(find "$d" -mmin "-$((max_age_hours * 60))" -print -quit 2> /dev/null)" ]; then
      continue
    fi
    kb=$(du -skx "$d" 2> /dev/null | awk '{ print $1 }')
    if rm -rf -- "$d"; then
      removed_kb=$((removed_kb + ${kb:-0}))
      echo "sweep-runner-tmp: removed $d (unchanged for over $max_age_hours hours)"
    else
      warn "could not remove $d"
    fi
  done < <(find "$dir" -mindepth 1 -maxdepth 1 -type d -user "$me" \( "${name_args[@]}" \) -print0)
done
echo "sweep-runner-tmp: freed $((removed_kb / 1024)) MB"
exit 0
