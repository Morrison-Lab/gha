- `condor-batch` gains an `output` input (`CONDOR_OUTPUT` for the script):
  a path inside the checkout, such as `_site`, that the cluster job packs into one tarball.
  HTCondor file transfer returns the tarball, and the runner unpacks it at the same path before deleting the run directory (gha#1554).
  With no `output`, only the log comes back, as before.
