- **`claude-code-review` no longer republishes a raw `gh pr comment` command as
  the review body** (#318). When the agent posts its own review via a
  `gh pr comment N --body "$(cat <<EOF ... EOF)"` Bash call (a trusted candidate
  when `permission_denials_count` is 0), `check-review-execution.sh` took the
  whole command string as the review text, so the "Claude finished review"
  summary comment showed a literal `gh pr comment ... <<EOF ...` block next to
  the correctly-posted review - the review appeared twice, once mangled. The
  guard now unwraps the heredoc body from such a command before using it as the
  posted text, falling back to the command unchanged when there is no heredoc.
  The terminator is located by comparing whole lines against the tag, the way
  bash itself ends a heredoc, so a review body containing a line that merely
  *starts* with the tag cannot cut the posted review short; the `<<-` form's
  leading-tab stripping is mirrored too. Both the posted text and the pass/fail
  scan still draw from the same block, so the gha#218 same-source invariant
  holds. Regression fixtures `verdict-via-gh-comment-heredoc.json`,
  `verdict-via-gh-comment-heredoc-tag-in-body.json`, and
  `verdict-via-gh-comment-heredoc-dash-tab.json` added (seen on
  [`UCD-SERG/serocalculator#614`](https://github.com/UCD-SERG/serocalculator/pull/614)).
