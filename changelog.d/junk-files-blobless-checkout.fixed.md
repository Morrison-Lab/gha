- `check-junk-files.yml` now checks out without file contents
  (`filter: blob:none`, with only `.github/` in a non-cone sparse checkout).
  The scan reads only the index,
  so a repository of large files (Morrison-Lab/mlr's PDFs)
  no longer runs past the 20-minute job timeout downloading blobs the scan never opens.
