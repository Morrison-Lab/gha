- **`claude-code-review.yml`: the Morrison-Lab content rules now include a clause-level line-break rule.**
  Rule 12 blocks a prose line the diff adds or changes that holds more than one clause.
  The `check-new-line-breaks` regex check is looser than the lab's rule, so the reviewer enforces the clause-level reading.
