- **The `gha-runner@` systemd unit now runs each self-hosted runner at nice 10 with idle I/O priority,**
  and sets `CPUWeight=50` and `MemoryHigh=3G` where the user manager delegates those controllers (#1509).
  A burst of simultaneous jobs on one host pushed cf463-02 to load 18 on 16 cores with its swap nearly full.
  Re-run `scripts/install-runner-systemd-unit.sh` to pick up the new unit file,
  then restart each instance between jobs.
