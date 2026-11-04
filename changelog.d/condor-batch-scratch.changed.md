- **`condor-batch` now runs each job in the execute node's scratch directory, using HTCondor file transfer**.
  WWU CS IT asks that jobs avoid heavy home-directory I/O.
  The action used to copy the whole checkout to the cluster home and run the job there,
  with the uv caches and render outputs on the home,
  which filled its 5 GB quota.
  It now packs the checkout into one tarball (`RSYNC_EXCLUDE` patterns are left out),
  copies that file and the steps file to the run directory,
  and has HTCondor transfer them into scratch, where the job unpacks them and runs every step.
  A new `REQUEST_DISK` variable (default 20GB) sizes the scratch space.
  Nothing is transferred back except the log.
