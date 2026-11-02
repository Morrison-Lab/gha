- **New `condor-batch` script**
  ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)).
  `condor-batch/condor-batch.sh <checkout> <steps-file>` rsyncs a checkout to
  `/cluster/home/morri313/ci/<run>/` on a cse or csci head node and runs every
  step in the file as one HTCondor job in one slot, then streams the log back.
  A file with fewer than two steps is refused, so tiny jobs stay on the
  runner instead of crowding the cluster queue.
  The cf463 home is not visible on the cluster, hence the copy.
  `hostname` prints nothing on the execute nodes (`uname -n` works), so steps
  should use `uname -n`.
