#!/usr/bin/env bash
# check-one-function-per-file: allow-multiple
# Run a command (an R package install) while holding a per-user lock, after
# deleting stale R install locks (gha#1311, gha#1409).
#
# Self-hosted runners of one user share one R library. Two jobs that install
# there at once collide on <lib>/00LOCK-<pkg> ("failed to lock directory") and
# can leave a corrupt lazy-load database. A killed install leaves its 00LOCK-*
# behind, and on a shared home it never clears itself.
#
# Usage: scripts/with-r-install-lock.sh COMMAND [ARGS...]
#
# While the lock is held no other wrapped install runs, so any 00LOCK* older
# than R_INSTALL_STALE_MINUTES (default 10) in a library is stale and is deleted.
# Environment:
#   R_INSTALL_LOCK_FILE     lock file (default ${XDG_CACHE_HOME:-$HOME/.cache}/gha-r-install.lock)
#   R_INSTALL_LOCK_TIMEOUT  seconds to wait for the lock (default 1800)
#   R_INSTALL_STALE_MINUTES age after which a 00LOCK* is stale (default 10)
#   R_INSTALL_LIB_DIRS      colon-separated libraries to sweep
#                           (default: .libPaths() of Rscript, plus R_LIBS_USER)
set -euo pipefail

if [ "$#" -eq 0 ]; then
  echo "usage: $0 COMMAND [ARGS...]" >&2
  exit 2
fi

lock_file="${R_INSTALL_LOCK_FILE:-${XDG_CACHE_HOME:-$HOME/.cache}/gha-r-install.lock}"
timeout_s="${R_INSTALL_LOCK_TIMEOUT:-1800}"
stale_min="${R_INSTALL_STALE_MINUTES:-10}"
mkdir -p "$(dirname "$lock_file")"

if ! command -v flock >/dev/null 2>&1; then
  echo "::warning::flock not found; running without the R install lock"
  exec "$@"
fi

exec 9>"$lock_file"
if ! flock -w "$timeout_s" 9; then
  echo "::error::waited ${timeout_s}s for the R install lock $lock_file"
  exit 1
fi

lib_dirs="${R_INSTALL_LIB_DIRS:-}"
if [ -z "$lib_dirs" ]; then
  lib_dirs="${R_LIBS_USER:-}"
  if command -v Rscript >/dev/null 2>&1; then
    paths="$(Rscript -e 'cat(.libPaths(), sep = ":")' 2>/dev/null || true)"
    lib_dirs="${lib_dirs:+$lib_dirs:}$paths"
  fi
fi

IFS=':' read -r -a libs <<<"$lib_dirs"
for lib in "${libs[@]}"; do
  [ -d "$lib" ] || continue
  while IFS= read -r stale; do
    [ -n "$stale" ] || continue
    echo "Removing stale R install lock $stale"
    rm -rf -- "$stale"
  done < <(find "$lib" -maxdepth 1 -name '00LOCK*' -type d -mmin "+$stale_min" 2>/dev/null)
done

# The lock stays held while the command runs: fd 9 is inherited, not closed.
"$@"
