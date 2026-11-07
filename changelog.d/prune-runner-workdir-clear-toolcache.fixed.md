- **`prune-runner-workdir.sh` clears the toolcache when the work folder moves.**
  The scripts in `<work>/_tool` carry absolute shebangs,
  so a toolcache copied from the old folder failed with "required file not found"
  while `setup-python` reused it (gha#1569).
  The hook records the work folder in `_tool/.work-folder`
  and removes `_tool` once when the recorded path differs.
  With no marker it only records the path and deletes nothing.
