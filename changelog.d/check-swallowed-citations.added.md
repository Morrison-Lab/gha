- **`check-swallowed-citations`**
  (Morrison-Lab/lds#3239):
  add a diff-scoped composite action and reusable workflow
  that fails when a pull request follows an in-text cross-reference
  with a citation bracket, such as `@eq-x [@key, section 3]`.
  Pandoc reads the pair as one citation,
  so the cited source drops out of the rendered page with no warning.
  Only spaces or one line break between the two count;
  punctuation, a blank line, a link, and a cross-reference inside a bracket pass,
  and `<!-- check-swallowed-citations: allow: <reason> -->` marks a deliberate use.
  Blocks by default; only lines a PR adds count.
