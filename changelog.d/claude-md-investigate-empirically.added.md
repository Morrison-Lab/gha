- **`CLAUDE.md` gains a "Never just theorize -- investigate empirically"
  section.** A hypothesis that is cheap to test has to be tested before it is
  asserted, and the section records the three checks that would have short-cut
  the org-move debugging: read a failed job's own error banner (reachable with
  `WebFetch` when the API will not serve it), read a checker's config before
  modelling its behavior, and prefer a run's own output to inference about it.

  It also records that a run of access failures is not evidence a question is
  unanswerable -- during that work three authenticated routes failed in a row
  before a plain public URL answered it immediately.
