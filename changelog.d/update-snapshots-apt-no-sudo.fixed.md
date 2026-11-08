- **`update-snapshots`** skips its apt step when every listed package is already installed,
and fails with a message naming the missing packages when apt would need sudo the runner lacks,
so a private runner with the packages preinstalled no longer fails at "Install apt packages" (gha#1694).
