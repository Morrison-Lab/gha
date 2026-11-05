#!/usr/bin/env bash
# Install the daily temp-folder sweep as systemd --user units (gha#1495).
# Usage: bash scripts/install-runner-tmp-sweep.sh
# Copies the script and units under ~/.local/share/gha and ~/.config/systemd/user,
# then enables the timer. Needs no sudo; loginctl enable-linger (gha#1425)
# keeps it running after logout. Idempotent.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
share="${XDG_DATA_HOME:-$HOME/.local/share}/gha"
units="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
mkdir -p "$share" "$units"
install -m 755 "$SCRIPT_DIR/sweep-runner-tmp.sh" "$share/sweep-runner-tmp.sh"
install -m 644 "$SCRIPT_DIR/gha-runner-tmp-sweep.service" "$units/"
install -m 644 "$SCRIPT_DIR/gha-runner-tmp-sweep.timer" "$units/"
if [ "${SKIP_SYSTEMCTL:-}" = 1 ]; then
  echo "Installed the units; skipped systemctl."
  exit 0
fi
systemctl --user daemon-reload
systemctl --user enable --now gha-runner-tmp-sweep.timer
echo "Enabled gha-runner-tmp-sweep.timer."
