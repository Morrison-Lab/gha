- `find-fallback-verdict.py`: a fallback review comment from a `CONTRIBUTOR` now counts when the collaborator-permission API reports write, maintain, or admin for its author.
  An admin whose org membership is private is reported as `CONTRIBUTOR`, so every fallback review they posted was skipped (gha#2032).
  Every other requirement is unchanged.
