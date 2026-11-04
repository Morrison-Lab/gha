- **`condor-batch` stops its cluster job and removes its run directory when the workflow run is cancelled**.
  A cancelled run killed the script but not the HTCondor job, which kept running
  and kept its run directory in the cluster home, whose quota filled.
  The script now records the cluster id, and on SIGTERM, SIGINT, or SIGHUP it runs `condor_rm` and deletes the directory.
  The stale-directory sweep's default age is now 60 minutes.
