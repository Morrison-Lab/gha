- **`claude-code-review.yml`: the Morrison-Lab content rules now include a result-type rule.**
  Rule 13 suggests a different type for a result div whose type the page's own use contradicts
  (a lemma the page cites only in prose, a theorem that restates an elementary identity),
  following psw's rule for choosing theorem, proposition, lemma, or corollary (Morrison-Lab/psw#668).
  It blocks a result that a page states twice, under two ids or two types.
  `check-corollary-sources` covers a corollary that names no earlier result.
