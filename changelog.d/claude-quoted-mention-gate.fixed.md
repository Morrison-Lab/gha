- **`claude.yml` no longer invokes the agent for an `@claude` mention that is
  merely being quoted** (gha#342).
  The job's `if:` tests the raw body with `contains()`, which has no notion of
  Markdown, so a mention inside a code span, a fenced code block, or a
  blockquote read exactly like one addressed to the bot.
  Writing *about* the bot therefore invoked it, and the cost compounded: the
  spawned run re-dispatches a review, and the per-pull-request
  `cancel-in-progress` group makes that cancel whichever review was already in
  flight -- so a comment explaining the concurrency race reproduced it.
  A new `detect-bot-mention` composite action strips those constructs and the
  job stands down when no mention survives.
  An `if:` expression cannot strip markup, so the raw `contains()` stays as a
  cheap pre-filter and the real decision now happens inside the job.
- **The gate errs toward running.**
  It stands down only when *every* occurrence sat inside markup; anything else
  proceeds, including an empty or missing result from the check itself.
  A genuine request that goes unanswered is a far worse outcome than a run
  that turns out to be unnecessary, which is the opposite of the bias the
  `@claude review` matcher uses and is deliberate in both places.
- **The two reasons a run can stand down are now decided in one place.**
  The late-comment dedup flag and this gate feed a single
  "Decide whether this run should proceed" step, so the workflow's downstream
  steps keep one condition each instead of repeating a compound one.
