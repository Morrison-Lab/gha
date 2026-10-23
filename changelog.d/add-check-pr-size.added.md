- `check-pr-size`:
  add a diff-scoped, blocking composite action and reusable workflow that fails a pull request changing more than 10 files or 300 lines (added plus deleted)
  ([#1188](https://github.com/Morrison-Lab/gha/issues/1188)).
  Every PR should be as small and focused as it can be while completely solving its task, and a sweep goes out as minimal batches.
  Generated, lock, image and data paths are not counted, and the `size-exempt` label, read live through the API, lifts the cap.
  Like its siblings it skips rather than measuring the whole tree when there is no base to diff against.
