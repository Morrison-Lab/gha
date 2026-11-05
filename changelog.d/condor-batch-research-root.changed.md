- **`condor-batch` now stages each run in the research directory, not the cluster home**.
  The default `CLUSTER_CI_ROOT` is `/cluster/research-groups/morrison/lds-ci`.
  It used to be `/cluster/home/morri313/ci`, and the 5 GB home quota made the copy fail with "Disk quota exceeded".
  WWU CS IT's account note says the home is for personal config files and the 5 TB research directory can stage files for CI/CD jobs.
  Jobs still run in the execute node's scratch directory through HTCondor file transfer.
  `CONDOR_IMAGE` still names a path the caller chooses, so images that live under the old root keep working until they move.
