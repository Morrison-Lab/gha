- `condor-batch` refuses a `CONDOR_OUTPUT` path with whitespace, quotes, a backslash, an absolute path, or `..` (exit 64) instead of writing a malformed submit file.
  The job script also says so when packing the output fails, so a full scratch disk is no longer hidden behind "could not bring ... back" (gha#1601).
