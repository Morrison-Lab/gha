- **New `condor-batch` script, internal for now**
  ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)).
  It has no reference page or caller stub yet.
  `condor-batch/condor-batch.sh <checkout> <steps-file>` rsyncs a checkout to
  `/cluster/home/morri313/ci/<run>/` on a cse or csci head node.
  It runs every step in the file as one HTCondor job in one slot.
  It then streams the log back.
  A file with fewer than two steps is refused.
  Tiny jobs then stay on the runner instead of crowding the cluster queue.
  The cf463 home is not visible on the cluster, hence the copy.
  A job that is held, removed or aborted exits 3.
  A `CONDOR_SSH_KEY` path containing whitespace is refused with exit 64.
  `hostname` prints nothing on the execute nodes, so steps should use `uname -n`.
