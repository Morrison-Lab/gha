- **`jules-review` no longer reports current dates as future-dated typos**
  (#366).
  The workflow now passes an `extra_instructions` block telling the reviewer it
  cannot reliably know today's date.
  Without it, every dated `CLAUDE.md` entry and changelog fragment -- both
  repo conventions -- drew a `[NIT]` claiming the date was a typo, and the
  finding survived rebuttal across review rounds.
