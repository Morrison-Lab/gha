- `check-self-reference`:
  add a diff-scoped, failing-by-default composite action and reusable workflow that flags self-referential prose
  when a pull request adds it: a sentence that starts with "This" or "These", a structural noun
  (exercise, solution, section, chapter, lecture, page, handout) and a verb such as
  shows, establishes, explains, covers or "is about".
  The rule is in psw, "Avoid forward references" (Morrison-Lab/psw#465).
  Code fences, comments and front matter do not count,
  and `<!-- check-self-reference: allow -->` exempts a line.
  Like `check-heading-titles` it scopes to added lines,
  skips rather than scanning the whole tree when there is no base to diff against,
  and has a `whole-tree` mode.
