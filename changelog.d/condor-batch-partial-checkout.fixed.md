- `condor-batch` no longer runs a job's steps on a partial checkout
  (Morrison-Lab/lds#3285).
  When the checkout is a git work tree missing tracked files,
  the script stops before contacting the cluster,
  names the first missing paths, and exits 75,
  which the action does not rerun on the runner.
  When the job cannot extract the checkout (a full scratch disk, a truncated transfer),
  it exits 74 without running a step,
  and the runner reruns the steps itself, as for any other code 70.
