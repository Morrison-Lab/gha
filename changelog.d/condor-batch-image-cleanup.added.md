- **`condor-batch` runs steps inside an Apptainer image and cleans up after itself**
  ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)).
  `CONDOR_IMAGE` names an image on the cluster home.
  When it is set, every step runs in it with the checkout bound at `/work`,
  and with the home, `TMPDIR` and the uv caches under `/work`,
  because the contained home and `/tmp` are small tmpfs.
  The run directory is now deleted when the job ends normally, whatever a step exited with,
  so runs stay inside the cluster home's quota.
  A job that did not end normally keeps its directory so `condor.log` can be read.
- **`condor-batch` composite gains an `image` input** ([#1381](https://github.com/Morrison-Lab/gha/issues/1381)). It sets `CONDOR_IMAGE` for the script. A failed delete of the run directory now prints a message and no longer replaces the job's exit code.
