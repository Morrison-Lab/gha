- **`claude-code-review.yml`: the Morrison-Lab content rules now include a clause-level line-break rule.**
  Rule 12 blocks a prose line of notes content with two or more clauses.
  The diff must add or change the line.
  The `check-new-line-breaks` regex check is looser than the lab's rule.
  The reviewer therefore enforces the clause-level reading.
  The rule is blocking, unlike the repository's general guidance to raise line-break nits as suggestions.
  The reason is the lab's policy.
  A wording or format nit blocks a merge on a notes site (Ezra, 2026-10-26).
  The rule overrides the cosmetic-formatting paragraph for those lines.
  It exempts headings, pipe-table rows, div headers, front-matter fields, captions, code fences, math, inline code and citation brackets.
  A "that" clause that completes its verb or adjective, or restricts a noun, is not a clause for this count.
