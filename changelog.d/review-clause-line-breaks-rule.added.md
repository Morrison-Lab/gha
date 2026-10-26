- **`claude-code-review.yml`: the Morrison-Lab content rules now include a clause-level line-break rule.**
  Rule 12 blocks a prose line the diff adds or changes that holds two or more independent clauses.
  It also blocks a main clause with its own subordinate clause.
  The `check-new-line-breaks` regex check is looser than the lab's rule.
  The reviewer therefore enforces the clause-level reading.
  The rule is blocking, unlike the repository's general guidance to raise line-break nits as suggestions.
  The reason is the lab's policy that a wording or format nit blocks a merge on a notes site (Ezra, 2026-10-26).
  For notes content it overrides the cosmetic-formatting paragraph.
