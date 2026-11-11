#!/usr/bin/env bash
# Supervise self-hosted runners with systemd --user, so a runner that exits (or
# whose login session ends) comes back within seconds (gha#1411). No sudo.
#
# Usage: [RUNNER_HOST=<host>] bash scripts/install-runner-systemd-unit.sh <instance>...
#   instance: the runner directory's suffix, so gate-1 means
#   ~/actions-runner-private-gate-1.
#   RUNNER_HOST: the only host allowed to start these instances; defaults to
#   this host (uname -n).
#
# Installs the template unit scripts/gha-runner@.service, pointed at this
# checkout's scripts/run-runner-exclusive.sh, turns on lingering so
# the units survive logout, and enables each instance. It does NOT stop a
# hand-launched listener: do that between jobs (SIGTERM, once the runner is
# idle), then `systemctl --user start gha-runner@<instance>`. Two listeners for
# one runner loop on "A session for this runner already exists".
#
# cf463-01 and cf463-02 share one home, so a unit enabled on one is enabled on
# both, and both hosts would start a listener for the same runner (gha#1543).
# Each instance therefore gets a drop-in with ConditionHost=RUNNER_HOST, so the
# other host's user manager skips it. Running this on the other host moves the
# instance there; stop it on the first host before starting it on the second.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
RUNNER_HOST="${RUNNER_HOST:-$(uname -n)}"
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <instance>..." >&2
  exit 2
fi
case "$RUNNER_HOST" in
  "" | *[!A-Za-z0-9.-]*)
    echo "RUNNER_HOST must be a host name, got '$RUNNER_HOST'." >&2
    exit 2
    ;;
esac
for instance in "$@"; do
  if [ ! -x "$HOME/actions-runner-private-$instance/run.sh" ]; then
    echo "No runner at ~/actions-runner-private-$instance." >&2
    exit 1
  fi
done
mkdir -p "$UNIT_DIR"
# The unit starts the runner through this checkout's run-runner-exclusive.sh.
sed "s#@GHA_SCRIPTS@#$SCRIPT_DIR#g" "$SCRIPT_DIR/gha-runner@.service" \
  > "$UNIT_DIR/gha-runner@.service"
for instance in "$@"; do
  dropin="$UNIT_DIR/gha-runner@$instance.service.d"
  mkdir -p "$dropin"
  printf '%s\n' "# Written by install-runner-systemd-unit.sh (gha#1543)." \
    "[Unit]" "ConditionHost=$RUNNER_HOST" > "$dropin/host.conf"
done
loginctl enable-linger "${USER:-$(id -un)}"
systemctl --user daemon-reload
for instance in "$@"; do
  systemctl --user enable "gha-runner@$instance"
done
echo "Enabled on $RUNNER_HOST only: $*. Start each after its hand-launched listener has stopped."
