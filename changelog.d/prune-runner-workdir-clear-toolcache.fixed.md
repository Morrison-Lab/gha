- **`prune-runner-workdir.sh` clears the Python toolcache when the work folder moves.**
  The scripts in `<work>/_tool/Python` carry absolute shebangs,
  so a toolcache copied from the old folder failed with "required file not found"
  while `setup-python` reused it (gha#1569).
  The hook records the work folder in `_tool/.work-folder`
  and removes `_tool/Python` and `_tool/PyPy` once when the recorded path differs,
  keeping other cached tools.
  A failed removal leaves the marker unchanged, so the next job retries.
  With no marker it only records the path and deletes nothing.
