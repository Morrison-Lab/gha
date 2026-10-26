- **`claude-code-review.yml`: the Morrison-Lab content rules now include a clause-level line-break rule.**
  Rule 12 blocks a prose line the diff adds or changes that holds two or more independent clauses, or a main clause with its own subordinate clause.
  The `check-new-line-breaks` regex check is looser than the lab's rule, so the reviewer enforces the clause-level reading.
  The rule is blocking, unlike the repository's general guidance to raise line-break nits as suggestions, because the lab's policy is that a wording or format nit blocks a merge on a notes site (Ezra, 2026-10-26).
  For notes content it overrides the cosmetic-formatting paragraph.
