- **The caller-side `if:` gate in `examples/claude.yml`,
  `website/reference/claude.qmd`, and this repo's own
  `.github/workflows/claude-bot.yml` now also checks `author_association`**
  (#259). Previously the caller-side gate only checked for an `@claude`
  mention in the triggering comment/review/issue, so any commenter — not
  just a trusted one — could spawn a run of the reusable workflow; its own
  trusted-author gate (`OWNER`/`MEMBER`/`COLLABORATOR`) still made the
  run's job skip, so no secrets were exercised, but the run still invoked
  a workflow granted elevated permissions and passed secrets. The gate now
  requires
  `contains(fromJSON('["OWNER","MEMBER","COLLABORATOR"]'), ...author_association)`
  alongside each event's mention check, mirroring the reusable workflow's
  own gate as defense-in-depth.
