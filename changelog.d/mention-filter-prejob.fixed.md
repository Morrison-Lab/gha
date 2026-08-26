- `claude.yml` gains a cheap `mention-filter` job that runs
  `detect-bot-mention` (the gha#342 stripper) and gates the agent job on its
  `proceed` output ([#554](https://github.com/Morrison-Lab/gha/issues/554)).

  A GitHub expression cannot strip Markdown, so the trusted-author `if:` is
  still formatting-blind and a quoted or code-span mention still starts the
  filter job.
  What it no longer starts is the expensive `claude` job -- no caller
  checkout, no R/Quarto setup, no model invocation.
  The filter runner minute is still billed.

  Assignment remains a sufficient trigger (gha#552): an allowlisted
  `issues.assigned` event proceeds even when the issue never mentions the
  bot.
  Unattended `workflow_dispatch`/`schedule` runs still dispatch: the filter
  job's `if:` admits those events, the detect step does not run (four empty
  bodies would print `false`), and an empty mention result fail-opens,
  matching the in-job contract gha#343 pinned.
