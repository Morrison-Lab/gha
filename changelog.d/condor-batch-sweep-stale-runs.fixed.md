- **`condor-batch` frees its own quota when a copy to the cluster fails**.
  A job that does not end normally keeps its run directory,
  and enough of them filled the cluster home's quota,
  after which every copy failed with "Disk quota exceeded"
  and every later run fell back to the runner.
  When a copy fails, the script now removes run directories older than `STALE_MINUTES` (default 120)
  and copies once more.
  Only digit-led directory names are removed, so an image directory beside them is kept.
