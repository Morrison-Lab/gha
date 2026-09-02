- **`claude-code-review` posts only the reviewer's last complete draft**
  (#805).
  A reviewer that redrafted its final message produced three complete
  reviews, each with its own `### Verdict` heading, and the gha#710 span
  rule concatenated all three into one comment.
  When more than one block carries an authored verdict heading (outside a
  code fence or blockquote, and indented at most three spaces), the posted
  text now starts at the last such block;
  a single heading, including gha#710's split-review shape, is unchanged.
