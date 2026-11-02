- **`cancel-superseded` reusable workflow cancels runs for old pull request heads**
  ([#1400](https://github.com/Morrison-Lab/gha/issues/1400)).
  On `synchronize` and `closed`, it cancels every other queued or running run of the pull request that was started for a head the pull request no longer has, or for a pull request that has closed.
  The caller needs `actions: write` and `pull-requests: read`.
