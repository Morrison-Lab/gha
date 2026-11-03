#!/usr/bin/env bash
# Supervise self-hosted runners with systemd --user, so a runner that exits (or
# whose login session ends) comes back within seconds (gha#1411). No sudo.
#
# Usage: bash scripts/install-runner-systemd-unit.sh <instance>...
#   instance: the runner directory's suffix, so gate-1 means
#   ~/actions-runner-private-gate-1.
#
# Installs the template unit scripts/gha-runner@.service, turns on lingering so
# the units survive logout, and enables each instance. It does NOT stop a
# hand-launched listener: do that between jobs (SIGTERM, once the runner is
# idle), then `systemctl --user start gha-runner@<instance>`. Two listeners for
# one runner loop on "A session for this runner already exists".
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
if [ "$#" -lt 1 ]; then
  echo "Usage: $0 <instance>..." >&2
  exit 2
fi
for instance in "$@"; do
  if [ ! -x "$HOME/actions-runner-private-$instance/run.sh" ]; then
    echo "No runner at ~/actions-runner-private-$instance." >&2
    exit 1
  fi
done
mkdir -p "$UNIT_DIR"
cp "$SCRIPT_DIR/gha-runner@.service" "$UNIT_DIR/gha-runner@.service"
loginctl enable-linger "$USER"
systemctl --user daemon-reload
for instance in "$@"; do
  systemctl --user enable "gha-runner@$instance"
done
echo "Enabled: $*. Start each after its hand-launched listener has stopped."
