- **`jules-review` no longer reports current dates as future-dated typos**
  (#366).
  The workflow now passes an `extra_instructions` block telling the reviewer it
  cannot reliably know today's date.
  Without it, the dates `CLAUDE.md` cites in its incident write-ups each drew a
  `[NIT]` claiming the date was a typo, and the finding survived rebuttal
  across review rounds.
