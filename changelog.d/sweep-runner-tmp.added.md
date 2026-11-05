- **Self-hosted runners sweep stale temp folders** --
  the job-completed hook and a daily `systemd --user` timer
  (`scripts/install-runner-tmp-sweep.sh`) now remove `Rtmp*` and `quarto-session*` folders
  that the runner user owns and nothing has changed in for 24 hours.
  Killed jobs had left about 65 GB of them in `/tmp` on cf463-01
  ([#1495](https://github.com/Morrison-Lab/gha/issues/1495)).
