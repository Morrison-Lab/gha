- `check-secrets` and `check-typos` retry their release downloads (gitleaks, typos)
  for about 80 s instead of 6 s, and on any error,
  so a release-host 504 burst no longer fails the job
  ([gha#1740](https://github.com/Morrison-Lab/gha/issues/1740)).
  This is the `v2` counterpart of the `cached_download` retry already on `main`.
