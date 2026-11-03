- **R package installs on self-hosted runners are serialized and clear stale locks.**
  `scripts/with-r-install-lock.sh` holds a per-user `flock` while a job installs R packages
  and deletes `00LOCK*` directories older than 10 minutes first,
  so two jobs sharing one R library no longer collide on `00LOCK-<pkg>` or leave a corrupt lazy-load database.
  The install steps of `lint-changed-lines`, `lint-changed-files`, `spellcheck`, `quarto-publish`,
  `preview` and `check-bibliography-dois` use it
  ([gha#1311](https://github.com/Morrison-Lab/gha/issues/1311),
  [gha#1409](https://github.com/Morrison-Lab/gha/issues/1409)).
