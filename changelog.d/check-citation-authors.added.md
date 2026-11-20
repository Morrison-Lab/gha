- **`check-citation-authors`**
  ([#2144](https://github.com/Morrison-Lab/gha/issues/2144)):
  add a diff-scoped composite action and reusable workflow
  that warns when a pull request types an author's surname
  next to a citation of the same source,
  such as `James et al. [@james2021islr, Figure 6.7]`,
  where `@james2021islr [Figure 6.7]` already prints the names
  (psw's "Let the citation name the source", psw#679).
  A capitalized word within six words before a citation key is flagged
  when the key starts with that word in lower case.
  An author-suppressed `[-@key]`, crossrefs, and names in link text or emphasis pass,
  and `<!-- check-citation-authors: allow: <reason> -->` marks a deliberate use.
  Warn-only by default; only lines a PR adds count.
