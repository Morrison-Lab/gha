- **`condor-batch` now runs each job in the execute node's scratch directory, using HTCondor file transfer**.
  WWU CS IT asks that jobs avoid heavy home-directory I/O.
  The action used to copy the whole checkout to the cluster home and run the job there.
  The uv caches and render outputs also went to the home, which filled its 5 GB quota.
  It now packs the checkout into one tarball, leaving out the `RSYNC_EXCLUDE` patterns.
  It copies that tarball and the steps file to the run directory.
  HTCondor then transfers both into scratch.
  There the job unpacks the tarball, then runs every step.
  A new `REQUEST_DISK` variable (default 20GB) sizes the scratch space.
  Nothing is transferred back except the log.
