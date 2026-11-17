- `check-avoided-words` fails on a line a pull request adds
  that uses a British spelling, such as "colour", "behaviour", "normalise",
  "centre", "modelling", or "labelled" (gha#2095, Ezra 2026-11-17).
  Quoted and italic text, links, crossrefs, ids, inline math,
  blockquotes, and code pass, so `colour =` in R and a British book title do not trip it.
  Only added lines are read, so existing uses do not trip it.
