- `check-result-titles`:
  add a composite action, with its reusable workflow, that flags the title of a theorem,
  lemma, proposition, corollary, or conjecture div when a pull request adds it
  and the title is not a declarative sentence stating the result (Ezra, 2026-11-20).
  A customary name may come first, followed by a colon.
  The test is a verb list plus math relations, not a parser,
  and `<!-- check-result-titles: allow: <reason> -->` exempts a line.
  The rule is in psw, "Title a result with the sentence it states".
  Like `check-heading-titles` it scopes to added lines, so existing titles are not swept,
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode.
  It fails by default.
  A second rule flags a result whose statement, the div's text after its title,
  has no display formula or no sentence in words,
  since the statement says the title's sentence again in both forms (Ezra, 2026-11-20).
  A statement finding is reported when a pull request adds any line of the div,
  and `<!-- check-result-titles: allow-statement: <reason> -->` in the div exempts it.
