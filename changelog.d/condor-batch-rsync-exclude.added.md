- **`condor-batch` takes an `RSYNC_EXCLUDE` environment variable**.
  It holds space-separated rsync patterns, such as `.git`, that are left off the cluster home when the checkout is copied.
  A checkout's `.git` pack files are the largest part of its copy,
  and several runs at once filled the cluster home's 5 GB quota.
