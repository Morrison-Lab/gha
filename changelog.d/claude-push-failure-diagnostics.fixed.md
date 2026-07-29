- **`claude` no longer discards a rejected push silently, or narrates it as a
  success** (#360). When the post-step push of Claude's commits is rejected --
  most often because `WORKFLOW_TOKEN` is unset and the change touches
  `.github/workflows/` -- the workflow now emits an error naming the missing
  secret and comments on the issue or PR with a `git format-patch` of the
  commits, which otherwise existed only on the runner. The
  "here is Claude's response" comment is also gated on the push having landed,
  so a failed push can no longer produce a comment describing work the branch
  does not carry.
