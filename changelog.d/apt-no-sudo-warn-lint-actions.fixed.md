- **`lint-changed-lines`, `lint-changed-files`, and `install-packages`** continue with a warning naming the packages,
instead of failing, when dpkg does not list an apt package and the runner has no passwordless sudo,
as `update-snapshots` does, so a runner that provides the libraries by another route is not stopped by the probe (gha#1699).
