- `scripts/install-runner-systemd-unit.sh` supervises self-hosted runners with a `systemd --user` template unit.
  A runner that exits, or whose login session ends, comes back within seconds with `~/.local/bin` on its PATH.
  Seven runners on cf463-02 had been started with `nohup` from a login session and all died when it ended (gha#1411).
