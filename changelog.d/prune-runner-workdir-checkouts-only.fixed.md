- **The runner cleanup hook removes only checkouts** --
  `scripts/prune-runner-workdir.sh` now deletes a work-folder directory only when it has the
  `<repo>/<repo>` layout the runner creates for a checkout.
  Before this, it deleted any directory not starting with `_`, so on a low disk it would also
  have removed the R library r-lib/setup-r keeps under `R/` (2 GB on cf463-01)
  ([#1352](https://github.com/Morrison-Lab/gha/issues/1352)).
