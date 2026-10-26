- **`claude-code-review.yml`: the Morrison-Lab content rules now include a presupposition rule.**
  The reviewer flags a definite noun phrase with no earlier antecedent or link, as a blocking finding on notes content.
  It also flags wording that presumes a conclusion the text has not shown.
  The warn-only `check-definite-antecedents` heuristic still covers only a div's first sentence.
  This rule covers the rest of the prose, on added lines only (gha#1232).
