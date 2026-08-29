- **`version-check`'s label exemption now reads the PR's labels live** (#722).
  It read `github.event.pull_request.labels` --- the labels frozen into the
  triggering event's payload --- so a `no version increment` label applied
  after that event never exempted, and approving or re-running a gated run
  reused the same stale payload, leaving the only runnable run unable to see
  the label.
  The read is fail-loud and case-insensitive, and matches the configured input
  label only: unlike #723's sibling fix for `check-news`, nothing downstream of
  this step recognizes a label of its own, so honouring a hardcoded spelling
  would defeat a caller's override.

- **Consumer note:** `version-check` already granted `pull-requests: read`, and
  that scope is now load-bearing --- it is what authorizes the label read.
  A caller that pins the calling job's `permissions` must include it alongside
  `contents: read`.
  `issues: read` is deliberately **not** required here: GitHub authorizes a
  label read on an issue object that is a pull request against the
  pull-requests permission, and `issues: read` alone returned 403 on
  `check-news`'s first consumer run (#724).
