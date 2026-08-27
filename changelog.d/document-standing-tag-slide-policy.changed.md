- **`CLAUDE.md` records the standing tag-slide grant** (#692).
  Agent sessions may dispatch `slide-major-tag.yml` on their own judgment,
  beside the existing standing `mwc` policy.
  The section ties the readiness bar to the same check-run reading `mwc` uses,
  requires re-reading `main`'s tip immediately before dispatch (the workflow
  tags `$GITHUB_SHA`, not a nominated commit), and pins the verification
  recipe against the remote, since a local tag read reports the pre-slide SHA.
