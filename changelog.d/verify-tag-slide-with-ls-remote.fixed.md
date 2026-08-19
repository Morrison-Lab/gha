- Docs: CLAUDE.md's "Re-running failed jobs cannot verify a tag slide" section
  now names how to read a tag's current commit reliably.
  It told the reader to compare a run's `referenced_workflows[].sha` against
  the tag's current commit without saying that `git fetch --tags` silently
  refuses to update an already-existing local tag,
  which is exactly what a slide does to it,
  so the check most likely to be run returned a stale value and read as
  "the slide has not happened"
  ([#522](https://github.com/Morrison-Lab/gha/issues/522)).
