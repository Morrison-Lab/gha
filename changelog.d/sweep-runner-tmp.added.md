- **Self-hosted runners sweep stale temp folders.**
  The job-completed hook removes `Rtmp*` and `quarto-session*` folders from `/tmp`.
  A daily `systemd --user` timer does the same (`scripts/install-runner-tmp-sweep.sh`).
  Both remove only folders that the runner user owns and nothing has changed in for 24 hours.
  Killed jobs had left about 65 GB of them on cf463-01
  ([#1495](https://github.com/Morrison-Lab/gha/issues/1495)).
