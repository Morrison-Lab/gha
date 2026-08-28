- `claude-code-review.yml`: incremental review rounds now receive a
  computed, authoritative what-changed-since-the-last-round section
  (#709).
  The workflow parses the prior verdict comment's machine-written
  `Reviewed commit:` line and runs `git log`/`git diff --stat` over the
  range itself,
  instructing the reviewer to describe that range rather than deriving
  its own;
  a reviewer-derived range has named one commit where the range held two
  and approved over the commit it missed.
  Empty on a first round or when the prior commit is unreachable in the
  checkout.
